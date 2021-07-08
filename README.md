# shared-row
This is an open data specification for describing the right-of-way (ROW) for street centerline networks. It is intended to establish a common set of attributes (schema) to describe how space is allocated along a streets right of way from sidewalk edge to sidewalk edge. Its goal is to enable a common language for describing streets cross-sections within a spatial database so that transportation professionals can compare high-level right of way summaries across jurisdictions, build applications on top of a common schema, or create queries about streets that would previously be hard to do. For example, with this specification, you could query which streets have bike lanes at least 5 ft wide with an 18 in painted buffer. 

# Goal
The goal of this specification is to enable transportation professionals, urban planners, and urban designers to create a common database schema to describe the right of way.
# Objectives
The specific objectives of this specification revolve around creating a common specification inspired by SharedStreets that helps to define the right-of-way (ROW) of a street. This specification also aims to provide ready to use tools to build these databases and develop crosswalks between different representations of the ROW.

These objectives can be identified specifically below:

1. Provide a common index based specification for describing sections of ROW using common descriptors. 
2. Describe a crosswalk that has a system of defaults built around taking existing data describing the ROW (OSM/Centerline Databases/Bicycle Facility Files), that creates default templates for ROW description that can be further edited and enhanced. 
3. Provide a high level data format that can connect project evaluation, prioritization, and design across multiple scales and disciplines that interact with transportation systems. 
4. Provide sample tools, services, and use cases that work across platforms (proprietary and open) so planners have the tools to build databases that conform to the shared-row-spec. 


# Problem Formulation 
The following section identifies challenges currently encountered in developing robust cross-sectional databases. 
## Additive vs. Sliced Data Representations
1. Most centerline databases (including OSM), are commonly represented by geometry with tabular attributes associated with them. They are *additive representations*, meaning they typically represent cross-sectional attributes as separate columns, where a value provided is an added value to the street. For example, a [bike lane](https://data.cityofnewyork.us/api/views/exjm-f27b/files/cba8af99-6cd5-49fd-9019-b4a6c2d9dff7?download=true&filename=Centerline.pdf) might be represented by a bicycle class designation (path,lane,shared lane), sometimes with [direction annotations]() of varying types. These data representations are typically "flat", meaning they are two-dimensional representations of attributes with one of the columns representing geometry. 
2. Many tools that develop cross-sections represent the cross-section using a *sliced representation*, where a list of cross-section attributes with meta-data attached (width, slice designation, heights) are associated with a single entity. These representations are hard to store in a flattened GIS database because the ordered list of slices and their attributes are hard to represent in standardized way in column based databases. Some of [these tools](https://github.com/streetmix/streetmix) do not associated geometry with their outputs, [some do](https://www.remix.com/streets), and [others](https://github.com/d-wasserman/Complete_Street_Rule) can create entire 3D representations based on their mapped parameters. 

# Specification-in-Brief

![alt text](../master/assets/SpecificationSample.JPG "Specification Sample")

* Line begin and end points determine street orientation
* Additive representations assume right vs left sides of a street are based on the perspective of an observer looking from LR1 to LR2
* Slice representations assume slices are described from left to right, with left vs. right based on the perspective from LR1 to LR2
* Linear units for fields are in Meters
* Each segment corresponds to a SharedStreetID, and a geometry that is a consolidated centerline (no dual-carriage ways). 
* SharedStreet intersections pedestrian crosswalks are associated with the segment they are intended to represent.
* Crosswalks will provide ways to move back and forth between Additive and Slice representations, enabling cities to maintain flexibility in terms of how they would maintain and edit a ROW database. 

#### For a more detailed description of the specification, check specification [here](../master/specification).

# Related Specifications & Databases

* [OpenStreetMap](https://www.openstreetmap.org/)
* [General Modeling Network Specification](https://github.com/zephyr-data-specs/GMNS/tree/updates)
* [MIRE Roadway Inventory Elements](https://safety.fhwa.dot.gov/rsdp/downloads/fhwasa17048.pdf)

# Related Projects

* [SharedStreets](https://www.sharedstreets.io/) (and the [CurbLR](https://github.com/sharedstreets/CurbLR) specification)
* [Streetmix](https://github.com/streetmix/streetmix)
* [CityEngine Complete Street Rule](https://github.com/d-wasserman/Complete_Street_Rule)
* [Remix Streets](https://www.remix.com/streets)
* [USDM StreetDesign Tool](https://usdm.upc.gov.ae/USDM/)
* [AB Street](https://github.com/dabreegster/abstreet)
