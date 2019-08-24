# -*- coding: utf-8 -*-

import arcpy


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "shared-row-tools"
        self.alias = "sharedrowtools"
        self.description = """This toolbox consists of a series of ArcGIS Scripts that enable the deployment of the
        shared-row-specification on to an appropriately defined centerline file. It includes tools to add compliant
        fields, add geodatabase domains, consolidate centerlines, convert the additive specification to a crosswalk
        file, and converting the crosswalk file into a geojson file compliant with the slice based specification."""

        # List of tool classes associated with this toolbox
        self.tools = [Add_Additive_Specification_Fields]


class Add_Additive_Specification_Fields(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Add shared-row-spec fields (Additive Specification)"
        self.description = """This script will add shared-row-spec fields that are compliant with the
        Additive Specification. The additive specification assumes each record is a single line geometry
        that represents right-of-way from segment to segment (no dual-carriageways)."""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        # First parameter
        param0 = arcpy.Parameter(
        displayName="Input Line Features",
        name="input_line_features",
        datatype="GPFeatureLayer",
        parameterType="Required",
        direction="Input")

        # Second parameter
        param1 = arcpy.Parameter(
        displayName="Add Optional Fields",
        name="optional_fields",
        datatype="Boolean",
        parameterType="Optional",
        direction="Input")
        # Set Values
        param1.values = True
        param0.filter.list = ["Polyline"]
        #Pass Parameters

        params = [param0,param1]
        return params


    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        return
