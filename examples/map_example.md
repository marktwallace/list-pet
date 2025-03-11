# Map Examples Using Metadata-Based Approach

## Example 1: Choropleth Map of US Counties

Assuming we have a dataframe with county-level data that includes FIPS codes and values:

```sql
-- Create a sample dataset with county data
CREATE TABLE county_data AS
SELECT 
  '01001' AS fips,
  'Autauga County' AS county_name,
  'AL' AS state,
  55.4 AS value
UNION ALL SELECT '01003', 'Baldwin County', 'AL', 62.3
UNION ALL SELECT '01005', 'Barbour County', 'AL', 42.1
UNION ALL SELECT '01007', 'Bibb County', 'AL', 48.7
UNION ALL SELECT '01009', 'Blount County', 'AL', 51.2;

-- Query the data
SELECT * FROM county_data;
```

Now we can create a choropleth map using the `<map>` element:

```
<map
  type: choropleth
  geojson: us_counties
  locations: fips
  color: value
  title: Sample County Data
  hover_data: [county_name, state]
  center: us
  color_continuous_scale: Viridis
  range_color: [0, 100]
/>
```

In this example:
- `geojson: us_counties` refers to a predefined GeoJSON source in our metadata
- `locations: fips` specifies which column in our dataframe contains the IDs that match the GeoJSON features
- The system automatically handles loading the GeoJSON file and matching it with our data

## Example 2: Scatter Map with Points

For a scatter map, we need latitude and longitude coordinates:

```sql
-- Create a sample dataset with point locations
CREATE TABLE city_data AS
SELECT 
  'New York' AS city,
  40.7128 AS latitude,
  -74.0060 AS longitude,
  8.4 AS value
UNION ALL SELECT 'Los Angeles', 34.0522, -118.2437, 7.2
UNION ALL SELECT 'Chicago', 41.8781, -87.6298, 6.8
UNION ALL SELECT 'Houston', 29.7604, -95.3698, 7.5
UNION ALL SELECT 'Phoenix', 33.4484, -112.0740, 8.1;

-- Query the data
SELECT * FROM city_data;
```

Now we can create a scatter map:

```
<map
  type: scatter_mapbox
  lat: latitude
  lon: longitude
  color: value
  size: value
  title: Major US Cities
  hover_data: [city]
  zoom: 3
  center: us
  mapbox_style: open-street-map
/>
```

## Querying Available GeoJSON Sources

To see what GeoJSON sources are available:

```sql
-- List available GeoJSON sources
SELECT * FROM _md_geojson_sources;

-- View properties of a specific GeoJSON source
SELECT * FROM _md_geojson_properties WHERE source_id = 'us_counties';
```

This metadata-driven approach allows for:
1. Consistent pattern with other elements like `<plot>`
2. Easy discovery of available GeoJSON sources
3. Automatic handling of file paths and feature ID properties
4. Separation of data (in dataframes) from geographic information (in GeoJSON files) 