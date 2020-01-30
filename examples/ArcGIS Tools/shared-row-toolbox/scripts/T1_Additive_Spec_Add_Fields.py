# --------------------------------
# Name: 1_Additive_Spec_Add_Fields.py
# Purpose: This tool will add all fields associated with the additive shared-row specification.
# Current Owner: David Wasserman
# Last Modified: 8/25/2019
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
import os
import sharedrowlib as srl


def add_additive_specification_fields_by_table(in_fc, csv, number_of_expandable_lanes=4, field_name_col="Name",
                                               type_col="Type", shp_field_name="Name_Shp", optional_col="Optional",
                                               optional_bool=True, validate=False):
    """This function will add additive shared-row specification fields based on a CSV. Uses Pandas.
    :param - in_fc - the input feature class that will have all the shared-row fields added to it.
    :param - csv - csv with field specification fields defined
    :param - number_of_expandable_lanes - while the minimum number of expandable lanes (through lanes) is 4, this
    parameter will enable the addition of more through lanes. This parameter does nothing if optional fields are not
    added
    :param - field_name_col - column of csv with field names being added
    :param - type_col - column of csv with the field type being added
    :param - shp_field_name - column of csv with field name to use if the file is a shapefile
    :param - optional_col - column of csv with a column identifying optional fields with a 1 and
    required fields as a 0
    :param - optional_bool - if true, optional fields will be added
    :param - validate - if true, all fields will go through a validate field routine
    """
    try:
        arcpy.env.overwriteOutput = True
        workspace = os.path.dirname(in_fc)
        df = pd.read_csv(csv)
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
            if fieldname[-1] == "X":
                if number_of_expandable_lanes > 4:
                    for i in range(5, int(number_of_expandable_lanes) + 1):
                        new_numeric_field = fieldname.replace("_X", "_{0}".format(i))
                        srl.add_new_field(in_fc, new_numeric_field, row[type_col])
                    continue  # Do not add X Field.
                else:
                    continue
            field_type = row[type_col]
            srl.add_new_field(in_fc, fieldname, field_type)
            if str(field_type).upper() == "TEXT":
                continue
            else:
                arcpy.AssignDefaultToField_management(in_fc, fieldname, 0)
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
    import os

    input_feature_class = arcpy.GetParameterAsText(0)
    number_of_expandable_lanes = int(arcpy.GetParameterAsText(1))
    optional_bool = bool(arcpy.GetParameterAsText(2))
    specification_data_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "specification_data")
    additive_csv = os.path.join(specification_data_dir, r"additive_shared_row_fields.csv")
    add_additive_specification_fields_by_table(input_feature_class, additive_csv, number_of_expandable_lanes,
                                               optional_bool=optional_bool)
