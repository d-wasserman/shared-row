# --------------------------------
# Name: 4_Slice_Spec_Exporter.py
# Purpose: This script tool will read in an input crosswalk feature class and convert it into a geojson
# Current Owner: David Wasserman
# Last Modified: 10/1/2019
# Copyright:   David Wasserman
# ArcGIS Version:   ArcGIS Pro/10.4
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
import sharedrowlib as srl
import json


def generate_slice_spec_geojson_file(input_features, sharedstreetid, slice_fields_csv, output_geojson):
    """This function will create a slice specification compliant geojson file.
    :param - in_features - feature class that has all of the fields from the crosswalk file
    :param - sharedstreetid - unique street ID as defined by SharedStreets.
    :param - slice_fields_csv - the csv with fields required for the slice specification compliant geojson.
    :param - output_geojson - output slice based geojson where each line geometry has slices as properties
    :return - output_geojson -path to output geojson
    """
    try:
        arcpy.env.overwriteOutput = True
        output_temp_features = os.path.join("in_memory", "Temporary_Slice_Features")
        srl.arc_print("Reading input features...")
        pre_fields = [f.name for f in arcpy.ListFields(input_features) if
                      f.type not in ["OID", "Geometry"] and f.name.lower()
                      not in ["shape_area", "shape_length"]]
        fields = ["SHAPE@"] + pre_fields
        cw_df = srl.arcgis_table_to_df(input_features, fields)
        cw_groups = cw_df.groupby(sharedstreetid)
        output_path, output_name = os.path.split(output_temp_features)
        arcpy.CreateFeatureclass_management(output_path, output_name, "POLYLINE")
        srl.arc_print("Adding fields to intermediate features...")
        slice_fields = srl.add_fields_from_csv(output_temp_features, slice_fields_csv)
        slice_fields = ["SHAPE@"] + slice_fields
        with arcpy.da.InsertCursor(output_temp_features, slice_fields) as insertCursor:
            srl.arc_print("Established insert cursor for intermediate slice file...", True)
            lineCounter = 0
            for street_id, street_group in cw_groups:
                lineCounter += 1
                try:
                    shape = street_group["SHAPE@"].iloc[0]
                    srl.arc_print(shape)
                    cw_fields = ["type", "width", "height", "direction", "material", "meta"]
                    slice_group = street_group[cw_fields]

                    json_slices = slice_group.to_json(orient="records")
                    srl.arc_print(json_slices)
                    slice_row = [shape, street_id, json_slices]
                    insertCursor.insertRow(slice_row)
                    if lineCounter % 500 == 0:
                        srl.arc_print("Iterated through feature " + str(lineCounter) + ".", True)
                except Exception as e:
                    srl.arc_print("Failed to iterate through feature " + str(lineCounter) + ".", True)
                    arcpy.AddWarning(str(e.args[0]))
            del insertCursor, fields, pre_fields, lineCounter
        srl.arc_print("Exporting intermediate feature class to geojson...")
        arcpy.FeaturesToJSON_conversion(output_temp_features, output_geojson, format_json=True, geoJSON=True,
                                        outputToWGS84=True, use_field_alias=True)
        srl.arc_print("Script Complete!")
    except Exception as e:
        srl.arc_print("Tool Script Error!")
        import traceback, sys
        tb = sys.exc_info()[2]
        srl.arc_print("An error occurred on line %i" % tb.tb_lineno)
        arcpy.AddError("The error occurred on line {0}...".format(tb.tb_lineno))


# End do_analysis function

# This test allows the script to be used from the operating
# system command prompt (stand-alone), in a Python IDE,
# as a geoprocessing script tool, or as a module imported in
# another script
if __name__ == '__main__':
    # Define input parameters
    import os

    input_features = arcpy.GetParameterAsText(0)
    sharedstreetid = arcpy.GetParameterAsText(1)
    output_geojson = arcpy.GetParameterAsText(2)
    specification_data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "specification_data")
    slice_csv = os.path.join(specification_data_dir, r"slice_shared_row_fields.csv")
    generate_slice_spec_geojson_file(input_features, sharedstreetid, slice_csv, output_geojson)
