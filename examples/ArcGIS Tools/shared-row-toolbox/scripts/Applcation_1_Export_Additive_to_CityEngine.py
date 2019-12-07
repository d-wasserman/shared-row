# --------------------------------
# Name: CE1_Create_Complete_Street_Rule_Features.py
# Purpose: This tool will extract data from ArcGIS Pro for CityEngine to use as attributes in the Complete Street Rule.
# If run fails: try closing input source and output source
# Current Owner: Tim Brown
# Last Modified: 12/6/2019
# Copyright:   Tim Brown & David Wasserman
# ArcGIS Version:   ArcGIS Pro/10.4
# Python Version:   3.5/2.7
# --------------------------------
# Copyright 2019 Tim Brown & David J. Wasserman
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
import sharedrowlib as srl



def generate_complete_street_attributes(input_features, output_features):
    """
    Create complete street rule attributes from the Additive Shared Spec
    @:param - input_features - text text
    @:param - output_features - text text
    @:param - null = 0 - text float
    """
    # try:
    arcpy.env.overwriteOutput = True
    srl.arc_print("Reading input features...")

    # Step 1 - create a copy of the feature class to a new output location
    arcpy.CopyFeatures_management(input_features, output_features)
    srl.arc_print("Adding Complete Street Rule Attribute fields...")
    # Step 2 - Add Fields to the feature class for the Complete Street Rule
    complete_street_attributes = ["streetWidth", "Center_Width", "sidewalkWidthRight", "sidewalkWidthLeft",
                                  "Left_Buffer_Width", "Left_Bike_Lane_Width", "Left_Parking_Width",
                                  "Right_Buffer_Width", "Right_Bike_Lane_Width",  "Right_Parking_Width"]
    complete_street_attributes_text = ["Center_Type", "Left_Buffer_Type", "Right_Buffer_Type"]
    for rule_attr in complete_street_attributes:
        srl.add_new_field(output_features, rule_attr, "DOUBLE")
    for rule_attr in complete_street_attributes_text:
        srl.add_new_field(output_features, rule_attr, "TEXT")
    # Step 3 - Use Update Cursor add values to fields based on Additive Fields
    fields = [f.name for f in arcpy.ListFields(output_features) if f.type not in ["OID"] and f.name.lower()
              not in ["shape", "shape_area", "shape_length"]]
    num_fields = [f.name for f in arcpy.ListFields(output_features) if f.type in ["Double", "Long", "Short", "Float"]]
    text_fields = [f.name for f in arcpy.ListFields(output_features) if f.type in ["Text"]]
    field_dictionary = srl.construct_index_dict(fields)
    print(field_dictionary)
    with arcpy.da.UpdateCursor(output_features, fields) as cursor:
        for row in cursor:
            # Set all None Values to Zero in Starting Row
            for field in num_fields:
                index = field_dictionary.get(field,None)
                if index is None:
                    continue
                value = row[index]
                if value is None:
                   row[field_dictionary.get(field)] = 0
            # Finding the Street Width
            center_lane_width = row[field_dictionary.get('Center_Lane')]
            left_bike_buffer_width = row[field_dictionary.get("Left_Bike_Buffer")]
            left_bike_lane_width = row[field_dictionary.get("Left_Bike_Lane")]
            left_transit_width = row[field_dictionary.get("Left_Transit_Lane")]
            left_parking_width = row[field_dictionary.get("Left_Parking_Lane")]
            right_bike_buffer_width = row[field_dictionary.get("Right_Bike_Buffer")]
            right_bike_lane_width = row[field_dictionary.get("Right_Bike_Lane")]
            right_parking_width = row[field_dictionary.get("Right_Parking_Lane")]
            right_transit_width = row[field_dictionary.get("Right_Transit_Lane")]
            # Support the 4 right and left through lanes
            LTL_List = [f.name for f in arcpy.ListFields(output_features) if "Left_Through_Lane" in f.name]
            LTL_Num_List = [row[field_dictionary.get(index)] for index in LTL_List
                            if row[field_dictionary.get(index)] is not None]
            Left_Lane_Widths = sum(LTL_Num_List)
            RTL_List = [f.name for f in arcpy.ListFields(output_features) if "Right_Through_Lane" in f.name]
            RTL_Num_List = [row[field_dictionary.get(index)] for index in RTL_List
                            if row[field_dictionary.get(index)] is not None]
            Right_Lane_Widths = sum(RTL_Num_List)
            # For Sidewalks Widths
            ls_frontage_width = row[field_dictionary.get("Left_Sidewalk_Frontage_Zone")]
            ls_furniture_width = row[field_dictionary.get("Left_Sidewalk_Furniture_Zone")]
            ls_through_width = row[field_dictionary.get("Left_Sidewalk_Through_Zone")]
            rs_frontage_width = row[field_dictionary.get("Right_Sidewalk_Frontage_Zone")]
            rs_furniture_width = row[field_dictionary.get("Right_Sidewalk_Furniture_Zone")]
            rs_through_width = row[field_dictionary.get("Right_Sidewalk_Through_Zone")]
            # Adding up all found values for sidewalk amd street scape.
            streetWidthValue = (center_lane_width + right_bike_lane_width + left_bike_lane_width +
                                left_parking_width + right_parking_width + Right_Lane_Widths + Left_Lane_Widths +
                                left_bike_buffer_width + right_bike_buffer_width
                                + right_transit_width + left_transit_width)
            sidewalkLeftValue = ls_frontage_width + ls_furniture_width + ls_through_width
            sidewalkRightValue = rs_frontage_width + rs_furniture_width + rs_through_width
            row[field_dictionary.get("streetWidth")] = streetWidthValue
            row[field_dictionary.get("Center_Width")] = center_lane_width
            row[field_dictionary.get("sidewalkWidthRight")] = sidewalkRightValue
            row[field_dictionary.get("sidewalkWidthLeft")] = sidewalkLeftValue
            # Update Fields to have bike lane, bike lane buffers, and bike lane buffer types OR parking lanes
            row[field_dictionary.get("Left_Bike_Lane_Width")] = left_bike_lane_width
            row[field_dictionary.get("Left_Buffer_Width")] = left_bike_buffer_width
            row[field_dictionary.get("Left_Parking_Width")] = left_parking_width
            row[field_dictionary.get("Right_Bike_Lane_Width")] = right_bike_lane_width
            row[field_dictionary.get("Right_Buffer_Width")] = right_bike_buffer_width
            row[field_dictionary.get("Right_Parking_Width")] = right_parking_width
            # Find if the text value is Null
            for field2 in text_fields:
                index2 = field_dictionary.get(field2, None)
                if index2 is None:
                    continue
                text = row[index2]
                if text is None:
                    row[field_dictionary.get(field2)] = "None"
            # Finds all Text fields that
            center_lane_type = row[field_dictionary.get("Center_Lane_Meta")]
            left_buffer_type = row[field_dictionary.get("Left_Bike_Buffer_Meta")]
            right_buffer_type = row[field_dictionary.get("Right_Bike_Buffer_Meta")]
            # Make the text values the CityEngine Complete Streets Attributes
            row[field_dictionary.get("Center_Type")] = center_lane_type
            row[field_dictionary.get("Left_Buffer_Type")] = left_buffer_type
            row[field_dictionary.get("Right_Buffer_Type")] = right_buffer_type
            cursor.updateRow(row)

            pass
    # Step 4 - Delete All Old Additive Fields
    fields_to_delete = [i for i in fields if i not in complete_street_attributes]
    arcpy.DeleteField_management(output_features, fields_to_delete)
    srl.arc_print("Script Complete!")
    # except Exception as e:
    #     srl.arc_print("Tool Script Error!")
    #     import traceback, sys
    #     tb = sys.exc_info()[2]
    #     srl.arc_print("An error occurred on line %i" % tb.tb_lineno)
    #     arcpy.AddError("The error occurred on line {0}...".format(tb.tb_lineno))


# End do_analysis function

# This test allows the script to be used from the operating
# system command prompt (stand-alone), in a Python IDE,
# as a geoprocessing script tool, or as a module imported in
# another script
if __name__ == '__main__':
    # Define input parameters
    import os
    input_feature_class = arcpy.GetParameterAsText(0)
    output_feature_class = arcpy.GetParameterAsText(1)
    generate_complete_street_attributes(input_feature_class,output_feature_class)

