# Download OSM data for Saint Petersburg regionc
curl.exe -L -o spb.osm.pbf https://download.geofabrik.de/russia/northwestern-fed-district-latest.osm.pbf

# Download GTFS data for Saint Petersburg
curl.exe -L --insecure --proto-default https -o spb-gtfs.zip "https://transport.orgp.spb.ru/Portal/transport/internalapi/gtfs/feed.zip"
