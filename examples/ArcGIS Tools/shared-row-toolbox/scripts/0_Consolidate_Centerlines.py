# --------------------------------
# Name: 0_Consolidate_Centerline.py
# Purpose: This tool is intended to help prepare line files for the shared-row-specification.
# Current Owner: David Wasserman
# Last Modified: 8/28/2019
# Copyright:   David Wasserman
# ArcGIS Version:   ArcGIS Pro
# Python Version:   3.5/2.7
# --------------------------------
# Copyright 2019 David J. Wasserman
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# --------------------------------

# Import Modules
import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
import os
import sharedrowlib as srl


def consolidate_centerline(in_fc, out_fc, out_consolidation_table, merge_field, merge_distance, sum_fields=[],
                           mean_fields=[], first_fields=[], concat_fields=[], character_field=None):
    """This function collapse a center line and compile collapsed fields using a combination of the the
    MergeDividedRoads tool in ArcGIS and pandas manipulation of its merge table.
    :param - in_fc - the input feature class that will be consolidated
    :param - out_fc - output consolidated feature class
    :param - out_consolidation_table - defaults to in memory, but the output table of consolidated lines
    :param - merge_field - usually a oneway field, this field identifies segments to merge with a 1, and locks those
    with a zero.
    :param - merge_distance - distance apart a line can be to consider for consolidation (avoid larger than a block)
    :param - sum_fields - based on the consolidation table created by the MergeDividedRoads tool, these fields will be
    attempted to be summed in a new field based on the two matching collapsed segments
    :param - mean_fields - based on the consolidation table created by the MergeDividedRoads tool, these fields will be
    attempted to be averaged in a new field based on the two matching collapsed segments.
    :param - first_fields - based on the consolidation table created by the MergeDividedRoads tool, these fields will be
    attempted to be first value found in a new field based on the two matching collapsed segments.
    :param - concat_fields - for text or categorical data these file
    :param - character_field - this field assists the MergeDividedRoads tool to merge roads appropriately. See
    ArcGIS DOCs.
    """
    try:
        arcpy.env.overwriteOutput = True
        workspace = os.path.dirname(in_fc)
        object_id_field = arcpy.Describe(in_fc).OIDFieldName
        srl.arc_print("Merging divided roads...")
        arcpy.MergeDividedRoads_cartography(in_fc, merge_field, merge_distance, out_fc, out_displacement_features=None,
                                            character_field=character_field, out_table=out_consolidation_table)
        srl.arc_print("Reading consolidation table...")
        output_fid, input_fid = "OUTPUT_FID", "INPUT_FID"
        consolidation_df = srl.arcgis_table_to_df(out_consolidation_table, [output_fid, input_fid])
        sql_query = "{0} in {1}".format(object_id_field, tuple(i for i in consolidation_df[input_fid].unique()))
        srl.arc_print("Reading input feature classes consolidated...")
        all_fields = sum_fields + mean_fields + first_fields + concat_fields
        all_fields = [i for i in all_fields if srl.field_exist(in_fc,i)] # Filter Non-Existent Fields
        consolidated_input_df = srl.arcgis_table_to_df(in_fc, all_fields, sql_query)
        consolidated_input_df = consolidated_input_df.merge(consolidation_df, how="left",
                                                            left_index=True, right_on=input_fid)
        srl.arc_print("Summarizing statistics of fields by the priority of sums,means, first, and concat...")
        consolidated_input_df_groups = consolidated_input_df.groupby(output_fid)
        agg_dict = {}
        new_columns = {}
        for field in all_fields:
            if field in sum_fields:
                agg_dict[field] = "sum"
                new_columns[field] = "sum_" + str(field)
            elif field in mean_fields:
                agg_dict[field] = "mean"
                new_columns[field] = "mean_" + str(field)
            elif field in first_fields:
                agg_dict[field] = "first"
                new_columns[field] = "first_" + str(field)
            else:
                agg_dict[field] = lambda x: ";".join(x)
                new_columns[field] = "concat_" + str(field)
        summarized_features = consolidated_input_df_groups.agg(agg_dict)
        summarized_features = summarized_features.rename(columns=new_columns)
        join_fields = list(summarized_features.columns)
        summarized_features = summarized_features.reset_index()
        temp_summary = os.path.join("in_memory", "summary_table")
        srl.arc_print("Exporting out summary table...")
        summarized_features.spatial.to_table(temp_summary)
        out_oid_field = arcpy.Describe(output_feature_class).OIDFieldName
        srl.arc_print("Joining summary fields to output...")
        join_field = "CenterID"
        arcpy.AddField_management(output_feature_class, join_field, "LONG")
        arcpy.CalculateField_management(output_feature_class, join_field, "!{0}!".format(out_oid_field))
        arcpy.JoinField_management(output_feature_class, join_field, temp_summary, output_fid, join_fields)
        srl.arc_print("Populating non-collapsed values with originals...")
        calc_func = """def fill_if_none(old_field, new_field):
            if new_field is None:
                return old_field
            else:
                return new_field 
    """
        for i in all_fields:
            arcpy.CalculateField_management(output_feature_class, new_columns[i],
                                            "fill_if_none(!{0}!,!{1}!)".format(i, new_columns[i]),"PYTHON"
                                            ,code_block=calc_func)
        srl.arc_print("Script Complete!")
    except Exception as e:
        srl.arc_print("Tool Script Error!")
        import traceback, sys
        tb = sys.exc_info()[2]
        srl.arc_print(e.args[0])
        arcpy.AddError("The error occurred on line {0}...".format(tb.tb_lineno))


# End do_analysis function

# This test allows the script to be used from the operating
# system command prompt (stand-alone), in a Python IDE,
# as a geoprocessing script tool, or as a module imported in
# another script
if __name__ == '__main__':
    # Define input parameters
    input_feature_class = arcpy.GetParameterAsText(0)
    output_feature_class = arcpy.GetParameterAsText(1)
    consolidation_table = arcpy.GetParameterAsText(2)
    merge_field = arcpy.GetParameterAsText(3)
    merge_distance = arcpy.GetParameterAsText(4)
    sum_fields = arcpy.GetParameterAsText(5).split(";")
    mean_fields = arcpy.GetParameterAsText(6).split(";")
    first_fields = arcpy.GetParameterAsText(7).split(";")
    concat_fields = arcpy.GetParameterAsText(8).split(";")
    character_field = arcpy.GetParameterAsText(9)
    consolidate_centerline(input_feature_class, output_feature_class, consolidation_table,
                           merge_field, merge_distance, sum_fields, mean_fields,
                           first_fields, concat_fields, character_field)
