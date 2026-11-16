import * as maplibregl from "https://unpkg.com/maplibre-gl@^6.16.0/dist/maplibre-gl.mjs";

async function getData(url) {
  const response = await fetch(url);
  return response.json();
}

const ceqr_data = await getData("data_cleaning/ceqr.geojson");

const map = new maplibregl.Map({
  container: "map", // container id
  style: "https://maps.gishub.org/styles/openstreetmap.json", // style URL
  center: [-73.9, 40.74], // starting position [lng, lat]
  zoom: 9, // starting zoom
});


map.on("load", async () => {
  map.addSource("ceqr", {
    type: "geojson",
    data: ceqr_data,
  });

  map.addLayer({
    id: "ceqr",
    type: "circle",
    source: "ceqr",
    paint: {
      "circle-radius": 5,
      "circle-color": "#3887be",
      "circle-stroke-width": 2,
      "circle-stroke-color": "#fff",
    }
  });
});

map.on("click", "ceqr", (e) => {

  const feature = e.features[0];

  const coordinates = feature.geometry.coordinates;
  const properties = feature.properties;

  // Zoom into the clicked point
  map.flyTo({
    center: coordinates,
    zoom: 16,
    speed: 1.2,
    curve: 1.4,
    essential: true
  });

  // Display information
  new maplibregl.Popup()
    .setLngLat(coordinates)
    .setHTML(`
      <h3>${properties.project_name}</h3>
      <p>${properties.project_status}</p>
      <p>Model info and other stuff would go here</p>
    `)
    .addTo(map);

});