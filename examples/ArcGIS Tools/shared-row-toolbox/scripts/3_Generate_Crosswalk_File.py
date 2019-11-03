# --------------------------------
# Name: 3_Generate_Crosswalk_File.py
# Purpose: This tool will create a crosswalk feature class where an Additive Specification Feature Class will  be
# converted into a flat table where the geometry is repeated, and each "slice" is a row repeated in a table. Slices
# are allocated based on a basic interpretation of the additive specification with indexes identifying slice order.
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
from collections import OrderedDict
import sharedrowlib as srl


def center_editor_function(insert_cursor, center_width, center_type, shape_length):
    """Given an insert cursor object, a center_width, shape_length, and center_type - this function will convert additive
    values into multiple slices with the appropriate tag values associated with them based on the additive
    specification's relationship to the slice specification.
    @:param- insert_cursor - cursor to add multiple slices too
    @:param - center_width - width of the total center allocation space to base approximations on
    @:param - center_type - type of center allocation
    @:param - shape_length - used to determine default values -if short enough, some tags are not added. """
    center_dict = {"end_depth": None, "begin_depth": None, "end_movements_allowed": "left",
                   "begin_movements_allowed": "left",
                   "remainder_allocation": None}
    return None


def add_fields_from_csv(in_fc, csv_path, field_name_col="Name", type_col="Type", shp_field_name="Name_Shp",
                        optional_col="Optional", optional_bool=True, validate=False):
    """Add fields to a feature class using arcpy based on the field names, types, shapefile name, and optional
    column in the CSV.
    :param - csv_path - path to the csv with fields to add
    :param - field_name_col - name of column with field names
    :param - type_col - name of column with field types
    :param - shp_field_name - name of the field to use if the file is a shapefile
    :param - optional_col - the column identify if a field is optional with a 1 and a 0 for not. 
    :param - optional_bool - if true add optional fields
    :param - validate- optional boolean controls whether field names are validated
     :return - list of fields added"""
    workspace = os.path.dirname(in_fc)
    df = pd.read_csv(csv_path)
    new_fields = []
    for index, row in df.iterrows():
        raw_field = str(row[field_name_col])
        if validate:
            fieldname = arcpy.ValidateFieldName(raw_field, workspace)
        else:
            fieldname = raw_field
        if shp_field_name and ".shp" in in_fc:
            fieldname = str(row[shp_field_name])
        if not optional_bool:
            if row[optional_col] == 1:
                print("Not adding optional field.")
                continue
        field_type = row[type_col]
        srl.add_new_field(in_fc, fieldname, field_type)
        new_fields.append(fieldname)
    return new_fields


def generate_crosswalk_file(in_features, output_features, slice_fields_csv, additive_spec_slice_order,
                            zone_meta_dict={}, conditional_meta_dict_update_functions={},
                            center_allocation_translator={}):
    """This function will add additive shared-row specification domains for categorical fields
     based on a CSV. Uses Pandas.
    :param - in_features - feature class that has additive specification fields for cross-walk creation
    :param - output_features - crosswalk feature class with indices indicating slices in an output feature class
    :param - slice_fields_csv - csv with fields to be added for the crosswalk file
    :param - additive_spec_slice_order - list of fields going from left to right to be added to the slice specification
    :param - zone_meta_dict - nested dictionaries - of key-value pairs where keys are additive width fields, and values
    are dictionaries indicating the values to fill the crosswalk type, heights, directions, etc. It takes the form of:
    {additive_field: {"type":value,"height":0,...}
    :param - conditional_meta_dict_update_functions - nested dictionaries - of key-value pairs where keys are meta
    of additive meta fields and their corresponding width field as a tuple, and values are a function used to
    conditionally modify the zone_meta_dict. If a meta tag is available, the zone_meta_dict will
    be modified based on that value.
    :param - center_allocation_translator - this dictionary of functions manages adding multiple slices from one
    additive attribute for center running features (median_with_turn_lane, can become multiple turn lanes and a median).
    :return - feature class where each geometry is copied and slices named based on additive specification
    """
    try:
        arcpy.env.overwriteOutput = True
        srl.arc_print("Reading input features...")
        pre_fields = [f.name for f in arcpy.ListFields(input_features) if f.type not in ["OID"] and f.name.lower()
                      not in ["shape_area", "shape_length"]]
        fields = ["SHAPE@"] + pre_fields
        cursor = arcpy.da.SearchCursor(in_features, fields)
        output_path, output_name = os.path.split(output_features)
        arcpy.CreateFeatureclass_management(output_path, output_name, "POLYLINE")
        srl.arc_print("Adding fields to crosswalk...")
        crosswalk_fields = add_fields_from_csv(output_features, slice_fields_csv)
        crosswalk_fields = ["SHAPE@"] + crosswalk_fields
        additive_dict = srl.construct_index_dict(fields)
        with arcpy.da.InsertCursor(output_features, crosswalk_fields) as insertCursor:
            srl.arc_print("Established insert cursor for crosswalk output feature class...", True)
            lineCounter = 0
            for index, street in enumerate(cursor, start=1):
                try:
                    segment_rows = []
                    lineCounter += 1
                    linegeo = street[0]
                    additive_slice_values = srl.retrieve_row_values(street, additive_fields_slice_order, additive_dict)
                    non_zero_width_fields = [(col, val) for col, val in
                                             zip(additive_spec_slice_order, additive_slice_values)
                                             if val]
                    slice_id = 0
                    sharedstreetid = street[additive_dict["SharedStreetID"]] if street[
                        additive_dict["SharedStreetID"]] else lineCounter

                    for field, width in non_zero_width_fields:
                        current_meta_field = str(field) + "_Meta"
                        if srl.field_exist(in_features, current_meta_field):
                            meta_tag_value = street[additive_dict[current_meta_field]]
                            zone_meta_dict[field].setdefault("meta", str({"type": meta_tag_value}))
                        type = zone_meta_dict.get(field, {}).get("type")
                        width = abs(float(width))
                        height = zone_meta_dict.get(field, {}).get("height", 0)
                        direction = zone_meta_dict.get(field, {}).get("direction", "bidirectional")
                        material = zone_meta_dict.get(field, {}).get("material", "asphalt")
                        meta = zone_meta_dict.get(field, {}).get("meta")
                        slice_row = [linegeo, sharedstreetid, slice_id, type, width, height, direction, material, meta]
                        segment_rows.append(slice_row)
                        slice_id += 1
                        insertCursor.insertRow(slice_row)
                    if lineCounter % 500 == 0:
                        srl.arc_print("Iterated through and split feature " + str(lineCounter) + ".", True)
                except Exception as e:
                    srl.arc_print("Failed to iterate through and a split feature " + str(lineCounter) + ".", True)
                    srl.arc_print(e.args[0])
            del cursor, insertCursor, fields, pre_fields, lineCounter
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
    output_features = arcpy.GetParameterAsText(1)
    specification_data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "specification_data")
    slice_csv = os.path.join(specification_data_dir, r"slice_shared_row_fields.csv")
    left_through_lanes = ["Left_Through_Lane_{0}".format(i) for i in range(1, 26)]
    right_through_lanes = ["Right_Through_Lane_{0}".format(i) for i in range(1, 26)]
    right_through_lanes.reverse()
    additive_fields_slice_order = ["Left_Sidewalk_Frontage_Zone", "Left_Sidewalk_Through_Zone",
                                   "Left_Sidewalk_Furniture_Zone", "Left_Bike_Lane", "Left_Bike_Buffer",
                                   "Left_Parking_Lane"] + left_through_lanes + ["Left_Transit_Lane", "Center_Lane",
                                                                                "Right_Transit_Lane"] + right_through_lanes + [
                                      "Right_Parking_Lane",
                                      "Right_Bike_Buffer", "Right_Bike_Lane", "Right_Sidewalk_Furniture_Zone",
                                      "Right_Sidewalk_Through_Zone", "Right_Sidewalk_Frontage_Zone", "Off_Street_Width"]
    zone_meta_dict = {}
    left_sidewalk_dicts = {i: {"type": "sidewalk", "height": 15.24, "material": "concrete", "direction": "reverse"}
                           for i in ["Left_Sidewalk_Frontage_Zone", "Left_Sidewalk_Through_Zone",
                                     "Left_Sidewalk_Furniture_Zone"]}
    right_sidewalk_dicts = {i: {"type": "sidewalk", "height": 15.24, "material": "concrete", "direction": "forward"}
                            for i in ["Right_Sidewalk_Furniture_Zone", "Right_Sidewalk_Through_Zone",
                                      "Right_Sidewalk_Frontage_Zone"]}
    left_drive_dict = {i: {"type": "drive_lane", "direction": "reverse"} for i in left_through_lanes}
    right_drive_dict = {i: {"type": "drive_lane", "direction": "forward"} for i in right_through_lanes}
    left_bike_lane_dict = {"Left_Bike_Lane": {"type": "bike_lane", "direction": "reverse"}}
    right_bike_lane_dict = {"Right_Bike_Lane": {"type": "bike_lane", "direction": "forward"}}
    left_buffer_dict = {"Left_Bike_Buffer": {"type": "buffer", "direction": "reverse"}}  # Meta?
    right_buffer_dict = {"Right_Bike_Buffer": {"type": "buffer", "direction": "forward"}}  # Meta?
    left_parking_dict = {"Left_Parking_Lane": {"type": "auto_parking"}, "direction": "reverse"}  # function to change?
    right_parking_dict = {"Right_Parking_Lane": {"type": "auto_parking"}, "direction": "forward"}  # function to change?
    left_transit_lane_dict = {"Left_Transit_Lane": {"type": "bus_lane", "direction": "reverse"}}  # meta change?
    right_transit_lane_dict = {"Right_Transit_Lane": {"type": "bus_lane", "direction": "forward"}}  # meta change?
    center_lane_dict = {"Center_Lane": {"type": "median", "height": 15.24, "material": "concrete"}}
    offstreet_dict = {"Off_Street_Width": {"type": "path", "material": "asphalt", "meta": "off-street facility"}}
    zone_meta_dict.update(left_sidewalk_dicts)
    zone_meta_dict.update(left_drive_dict)
    zone_meta_dict.update(left_bike_lane_dict)
    zone_meta_dict.update(left_buffer_dict)
    zone_meta_dict.update(left_parking_dict)
    zone_meta_dict.update(left_transit_lane_dict)
    zone_meta_dict.update(center_lane_dict)
    zone_meta_dict.update(right_transit_lane_dict)
    zone_meta_dict.update(right_parking_dict)
    zone_meta_dict.update(right_buffer_dict)
    zone_meta_dict.update(right_bike_lane_dict)
    zone_meta_dict.update(right_drive_dict)
    zone_meta_dict.update(right_sidewalk_dicts)
    zone_meta_dict.update(offstreet_dict)
    generate_crosswalk_file(input_features, output_features, slice_csv, additive_fields_slice_order, zone_meta_dict)
