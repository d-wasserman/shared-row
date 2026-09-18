"""Command line interface: ``python -m shared_row_parametric``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import additive as additive_mod
from . import crosswalk as crosswalk_mod
from . import io as io_mod
from . import metrics as metrics_mod
from . import operators as ops
from . import render as render_mod
from . import templates as templates_mod
from . import validate as validate_mod
from .model import CrossSection

PROG = "shared-row-parametric"


# --- helpers ----------------------------------------------------------------

def _write(text: str, out: Optional[str]) -> None:
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print("wrote %s" % out, file=sys.stderr)
    else:
        print(text)


def _emit(sections: Sequence[CrossSection], args) -> None:
    """Render sections in whichever output format was asked for."""
    fmt = args.format
    if fmt == "ascii":
        blocks = []
        for s in sections:
            head = s.sharedstreetid or "(no SharedStreetID)"
            blocks.append("%s\n%s" % (head, render_mod.to_ascii(s)))
        _write("\n\n".join(blocks), args.out)
        return
    if fmt == "svg":
        if len(sections) > 1 and not args.out:
            print("%d sections: writing only the first to stdout" % len(sections),
                  file=sys.stderr)
        _write(render_mod.to_svg(
            sections[0], title=sections[0].sharedstreetid or None), args.out)
        return
    if fmt == "summary":
        blocks = [metrics_mod.allocation(s).table() for s in sections]
        _write("\n\n".join(blocks), args.out)
        return
    rep = {"slice": io_mod.SLICE, "additive": io_mod.ADDITIVE,
           "crosswalk": io_mod.CROSSWALK}[fmt]
    collection = io_mod.dump(
        sections, rep,
        stringify_slices=not args.nested_slices,
        shapefile_names=args.shapefile_names,
    )
    _write(json.dumps(collection, indent=2), args.out)


def _add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", default="slice",
                   choices=["slice", "additive", "crosswalk", "svg", "ascii", "summary"],
                   help="output representation (default: slice)")
    p.add_argument("--out", help="write to this file instead of stdout")
    p.add_argument("--nested-slices", action="store_true",
                   help="emit slices as a real JSON array rather than the "
                        "string encoding used by the repository's samples")
    p.add_argument("--shapefile-names", action="store_true",
                   help="use 10-character shapefile-safe field names")


def _add_input_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("input", help="GeoJSON file in any shared-row representation")
    p.add_argument("--from", dest="source", default="auto",
                   choices=["auto", "slice", "additive", "crosswalk"],
                   help="input representation (default: auto-detect)")
    p.add_argument("--arrangement", default=additive_mod.DEFAULT_ARRANGEMENT,
                   choices=sorted(additive_mod.ARRANGEMENTS),
                   help="kerb-zone order when reading additive records")
    p.add_argument("--sample-compat", action="store_true",
                   help="read a furniture zone as a second sidewalk slice, as "
                        "the repository's sample data encodes it, rather than "
                        "as a planting_strip")


def _load(args):
    kwargs: Dict[str, Any] = {}
    if args.source in ("auto", "additive"):
        kwargs = {"arrangement": args.arrangement,
                  "semantic_furniture": not args.sample_compat}
    try:
        return io_mod.load(args.input, representation=args.source, **kwargs)
    except TypeError:
        return io_mod.load(args.input, representation=args.source)


# --- commands ---------------------------------------------------------------

def cmd_templates(args) -> int:
    lib = templates_mod.library(args.template_file)
    if args.name:
        tpl = templates_mod.get(args.name, args.template_file)
        print(json.dumps(tpl.to_dict(), indent=2))
        return 0
    print("%-26s %-7s %-7s %-7s %s" % ("name", "min", "pref", "max", "row range"))
    print("-" * 78)
    for name, tpl in sorted(lib.items()):
        rng = "%.0f-%.0f m" % tpl.row_range if tpl.row_range else "any"
        print("%-26s %-7.2f %-7.2f %-7.2f %s" % (
            name, tpl.min_width, tpl.preferred_width, tpl.max_width, rng))
        print("%s%s" % (" " * 4, tpl.description))
    return 0


def cmd_generate(args) -> int:
    tpl = templates_mod.get(args.template, args.template_file)
    result = tpl.fit(args.row_width, allow_drop=not args.no_drop,
                     sharedstreetid=args.sharedstreetid)
    if args.report:
        print(result.report.summary(), file=sys.stderr)
    if not result.report.feasible and not args.force:
        print("error: template does not fit in %.2f m (minimum %.2f m). "
              "Use --force to emit it anyway."
              % (args.row_width, result.report.resulting_width), file=sys.stderr)
        return 2
    _emit([result.section], args)
    return 0


def cmd_fit(args) -> int:
    if args.template:
        names = [args.template]
    else:
        names = [t.name for t in templates_mod.suggest(args.row_width, args.template_file)]
        if not names:
            print("no templates available", file=sys.stderr)
            return 1
    print("right-of-way: %.2f m\n" % args.row_width)
    for name in names:
        tpl = templates_mod.get(name, args.template_file)
        result = tpl.fit(args.row_width)
        alloc = metrics_mod.allocation(result.section)
        flag = "" if result.report.feasible else "  DOES NOT FIT"
        print("%s%s" % (name, flag))
        print("  " + result.section.describe())
        print("  auto %.0f%%  sustainable %.0f%%  %s" % (
            alloc.auto_share * 100, alloc.sustainable_share * 100,
            ("dropped: " + ", ".join(result.report.dropped))
            if result.report.dropped else "nothing dropped"))
        print()
    return 0


def cmd_convert(args) -> int:
    sections, rep = _load(args)
    print("read %d section(s) as %s" % (len(sections), rep), file=sys.stderr)
    _emit(sections, args)
    return 0


def cmd_validate(args) -> int:
    sections, rep = _load(args)
    result = validate_mod.validate_many(sections)
    if rep == io_mod.ADDITIVE:
        with open(args.input, "r", encoding="utf-8") as fh:
            collection = json.load(fh)
        extra = []
        for n, feature in enumerate(collection.get("features", [])):
            extra.extend(validate_mod.validate_additive(
                feature.get("properties") or {}, where="feature %d" % n).issues)
        result = validate_mod.Result(list(result.issues) + extra)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("%s: %d section(s), read as %s" % (args.input, len(sections), rep))
        print(result.report(min_level=args.min_level))
    return 0 if result else 1


def cmd_metrics(args) -> int:
    sections, _ = _load(args)
    if args.json:
        payload: Dict[str, Any] = {
            "network": metrics_mod.network_summary(sections),
            "segments": [
                dict(metrics_mod.allocation(s).to_dict(),
                     sharedstreetid=s.sharedstreetid)
                for s in sections
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0
    if len(sections) > 1:
        summary = metrics_mod.network_summary(sections)
        print("network: %d segments, %.0f m total length, mean ROW %.2f m"
              % (summary["segments"], summary["total_length_m"],
                 summary["mean_row_width_m"]))
        if summary.get("segments_without_geometry"):
            print("  (%d segment(s) without geometry counted at unit weight)"
                  % summary["segments_without_geometry"])
        print()
        print("%-13s %12s %8s" % ("mode", "area m2", "share"))
        print("-" * 35)
        for mode, area in sorted(summary["area_by_mode_m2"].items(),
                                 key=lambda kv: -kv[1]):
            print("%-13s %12.0f %7.1f%%"
                  % (mode, area, summary["share_by_mode"][mode] * 100))
        return 0
    print(metrics_mod.allocation(sections[0]).table())
    return 0


def cmd_diet(args) -> int:
    sections, _ = _load(args)
    after: List[CrossSection] = []
    for section in sections:
        new, report = ops.road_diet(
            section,
            keep_lanes=args.keep_lanes,
            bike_width=args.bike_width,
            buffer_width=args.buffer_width,
            protected=args.protected,
            remainder_to=args.remainder_to,
        )
        if args.coalesce:
            new = ops.coalesce(new)
        after.append(new)
        if len(sections) == 1:
            print(metrics_mod.compare(section, new).table(), file=sys.stderr)
            print(file=sys.stderr)
            print("freed %.2f m; %s" % (
                report["freed_m"],
                "width preserved" if report["width_preserved"]
                else "WIDTH CHANGED"), file=sys.stderr)
    _emit(after, args)
    return 0


def cmd_render(args) -> int:
    sections, _ = _load(args)
    args.format = args.renderer
    _emit(sections, args)
    return 0


# --- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Parametric cross-sections for the shared-row specification.",
    )
    parser.add_argument("--template-file", help="a JSON template library to use "
                                               "instead of the built-in one")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("templates", help="list or dump street archetypes")
    p.add_argument("name", nargs="?", help="dump this template as JSON")
    p.set_defaults(func=cmd_templates)

    p = sub.add_parser("generate", help="build a cross-section from a template")
    p.add_argument("template")
    p.add_argument("row_width", type=float, help="right-of-way width in metres")
    p.add_argument("--sharedstreetid")
    p.add_argument("--report", action="store_true", help="explain the allocation")
    p.add_argument("--no-drop", action="store_true",
                   help="fail rather than dropping slices to fit")
    p.add_argument("--force", action="store_true",
                   help="emit the section even if it does not fit")
    _add_output_args(p)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("fit", help="compare templates at a given width")
    p.add_argument("row_width", type=float)
    p.add_argument("--template", help="only this template")
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("convert", help="convert between representations")
    _add_input_args(p)
    _add_output_args(p)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("validate", help="check a file against the specification")
    _add_input_args(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--min-level", default="info",
                   choices=["error", "warning", "info"])
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("metrics", help="width and area allocation by mode")
    _add_input_args(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("diet", help="reallocate travel lanes to cycle tracks")
    _add_input_args(p)
    p.add_argument("--keep-lanes", type=int, default=1,
                   help="travel lanes to keep per direction (default: 1)")
    p.add_argument("--bike-width", type=float, default=1.8)
    p.add_argument("--buffer-width", type=float, default=0.6)
    p.add_argument("--protected", action="store_true",
                   help="place the cycle track outboard of parking")
    p.add_argument("--remainder-to", default="sidewalk",
                   help="slice type receiving leftover width (default: sidewalk)")
    p.add_argument("--coalesce", action="store_true",
                   help="merge adjacent slices of the same type afterwards")
    _add_output_args(p)
    p.set_defaults(func=cmd_diet)

    p = sub.add_parser("render", help="draw a cross-section")
    _add_input_args(p)
    p.add_argument("--renderer", default="svg", choices=["svg", "ascii"])
    p.add_argument("--out")
    p.set_defaults(func=cmd_render, format="svg", nested_slices=False,
                   shapefile_names=False)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
