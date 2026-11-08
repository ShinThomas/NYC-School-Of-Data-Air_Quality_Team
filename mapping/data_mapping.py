import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

pio.renderers.default = "browser"

tree_census = pd.read_csv("data/2015_Street_Tree_Census.csv")
forestry_points = pd.read_csv("data/Forestry_Tree_Points.csv")
traffic_volume = pd.read_csv("data/traffic_counts_with_coordinates.csv")
l84_disclosure = pd.read_csv("data/Law_84_Disclosure.csv")
open_aq = pd.read_csv("data/NYCOpenAQ.csv")
purple_air = pd.read_csv("data/purple_air_monthlypm25.csv")
cats = pd.read_csv("data/CATS.csv")
epa = pd.read_csv("data/epa_all_station_monthly_means.csv")


# Getting longitude and latitude for forestry points
lon = []
lat = []

for index, row in forestry_points.iterrows():
    coords = str(row["Location"])
    coords = coords.split("(")[1]
    y_cur = coords.split()[0].strip()
    x_cur = coords.split()[1].split("\\")[0].strip(")").strip()
    lat.append(x_cur)
    lon.append(y_cur)
    

forestry_points["latitude"] = lat
forestry_points["longitude"] = lon


# Drop duplicates from data that is taken multiple times from the same location
traffic_volume_map = traffic_volume.drop_duplicates(subset="SegmentID")
open_aq_map = open_aq.drop_duplicates(subset="Monitoring Station ID")
epa_map = epa.drop_duplicates(subset="station")
cats_map = cats.drop_duplicates(subset="Lot")
purple_air_map = purple_air.drop_duplicates(subset="sensor_index")

# Randomly sample forestry points since it's impossible to view it all at once
rand_forestry_points = forestry_points.sample(frac=0.25, replace=False, axis=0)

def map_data(df, latitude, longitude, color, title, fig, size, hover_text=None):
    if hover_text == None:
        fig.add_trace(go.Scattermap(
            lat=df[latitude],
            lon=df[longitude],
            mode='markers',
            marker=go.scattermap.Marker(
                size=size,
                color=color
            ),
            name=title
        ))
    else:
        fig.add_trace(go.Scattermap(
                    lat=df[latitude],
                    lon=df[longitude],
                    mode='markers',
                    marker=go.scattermap.Marker(
                        size=size,
                        color=color
                    ),
                    name=title,
                    text=hover_text,
                    hover_data="text"
                ))
    fig.update_layout(mapbox_style="open-street-map",
                  autosize=True,
                  map=dict(
                    bearing=0,
                    center=dict(
                        lat=40.6,
                        lon=-74
                    ),
                    pitch=0,
                    zoom=10,
    ))
    return


air_sensors = go.Figure()
map_data(open_aq_map, longitude="Longitude", latitude="Latitude", color="blue", title="Open AQ Data", fig=air_sensors, size=4)
map_data(epa_map, longitude="longitude", latitude="latitude", color="red", title="EPA Data", fig=air_sensors, size=4)
map_data(purple_air_map, longitude="longitude", latitude="latitude", color="purple", title="Purple Air", fig=air_sensors, size=4)
air_sensors.show()

building_data = go.Figure()
map_data(cats, longitude="longitude", latitude="latitude", color="blue", title="CATS", fig=building_data, size=3)
map_data(traffic_volume_map, longitude="longitude", latitude="latitude", color="red", title="Traffic Volume", fig=building_data, size=3)
map_data(l84_disclosure, longitude="Longitude", latitude="Latitude", color="purple", title="Law 84", fig=building_data, size=2)
building_data.show()

trees = go.Figure()
map_data(tree_census, longitude="longitude", latitude="latitude", color="green", title="Tree Census", fig=trees, size=2)
map_data(rand_forestry_points, longitude="longitude", latitude="latitude", color="lightgreen", title="Forestry Random 1", fig=trees, size=2)
trees.show()