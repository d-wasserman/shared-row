# Specification
The shared-row specification can be viewed in a few ways.

# Specification Markdown Tables
The specification is documented in these markdown tables updated on 10/26/2020. 

## Additive Specification Tables

**Description**: Consists of a line geometry file that is a flat table consisting of standardized right of way description fields. Each shared-row-id considered unique, and represents a single consolidated centerline for a street (no dual carriageways). Right oriented fields denote lanes enabling traffic in the forward direction towards the end point of the line, and left oriented fields denote lanes enabling traffic in the reverse direciton toward the start point of the line.  Provides a GIS/SQL compatible database schema.

**Markdown Table**:[Here](specification/MarkdownTables/Additive.md)

## Crosswalk Specification Tables
**Description**: A share-row-crosswalk consists of each row representing a slice of street sharing a common shared-street id. Intended to allow the conversion between Additive and Sliced based specifications in an editable GIS/SQL database. 
**Markdown Table**:[Here](specification/MarkdownTables/Crosswalk.md)

## Slice Specification Tables
**Description**: Represents a web readable geojson layer with both line geometry and nested slices identified. This helps create a web transferable layer for application development.  
**Markdown Table**:[Here](specification/MarkdownTables/Slice.md)

# Specification Excel Sheet
The specification is a work in progress currently being drafted in the excel sheet for easy of editing. You can download the sheet by clicking [here](specification/Shared-Row.xlsx). File an issue if you want to suggest an alternative.