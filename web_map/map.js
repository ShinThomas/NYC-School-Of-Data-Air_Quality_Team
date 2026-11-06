import * as maplibregl from "https://unpkg.com/maplibre-gl@^6.16.0/dist/maplibre-gl.mjs";

      const map = new maplibregl.Map({
        container: "map", // container id
        style: "https://maps.gishub.org/styles/openstreetmap.json", // style URL
        center: [-73.9, 40.74], // starting position [lng, lat]
        zoom: 9, // starting zoom
      });