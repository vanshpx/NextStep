# Bugfix Requirements Document: Incorrect Location Coordinates

## Introduction

The travel itinerary application displays activities and places on an interactive map. Currently, multiple activities that represent different physical locations are showing identical or nearly identical GPS coordinates in the seed data. This causes map markers to overlap at the same position, making it impossible for users to distinguish between different locations and interact with individual markers. This bug affects the map visualization feature across all itineraries, particularly impacting the user experience when viewing day-by-day activities on the map.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the seed data contains activities at different physical locations (e.g., "Anju Beach Resort & Spa" and "Sunset Cruise on Mandovi River") THEN the system assigns identical or nearly identical coordinates (lat: 15.5535, lng: 73.7634 vs lat: 15.5012, lng: 73.8274) causing markers to overlap on the map

1.2 WHEN multiple activities share the same coordinates despite being at different locations THEN the system renders overlapping map markers that cannot be individually selected or distinguished

1.3 WHEN users view the map with overlapping markers THEN the system fails to provide visual feedback indicating multiple locations exist at that position

1.4 WHEN the geocoding data in the seed file contains inaccurate coordinates for specific locations THEN the system persists these incorrect coordinates to the database without validation

### Expected Behavior (Correct)

2.1 WHEN the seed data contains activities at different physical locations THEN the system SHALL assign accurate, distinct GPS coordinates that correspond to each location's actual geographic position

2.2 WHEN each activity has unique, accurate coordinates THEN the system SHALL render individual map markers at their correct positions without overlap

2.3 WHEN users view the map with properly geocoded locations THEN the system SHALL display each marker at its distinct position, allowing individual selection and interaction

2.4 WHEN the seed file is executed THEN the system SHALL populate the database with verified, accurate coordinates for all activities, hotels, and flight locations

### Unchanged Behavior (Regression Prevention)

3.1 WHEN activities legitimately occur at the same location (e.g., "Check-in" and "Breakfast" both at the same hotel) THEN the system SHALL CONTINUE TO assign the same coordinates to both activities

3.2 WHEN the map component receives valid coordinate data THEN the system SHALL CONTINUE TO render markers correctly using the existing map visualization logic

3.3 WHEN users interact with map markers that have distinct coordinates THEN the system SHALL CONTINUE TO display activity details and allow marker selection as currently implemented

3.4 WHEN the seed script runs THEN the system SHALL CONTINUE TO follow the existing database schema and data structure for storing location information
