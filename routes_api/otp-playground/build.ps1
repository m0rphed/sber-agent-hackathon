docker run --rm -v "$PWD/data:/var/opentripplanner" opentripplanner/opentripplanner:2.8.1 --build --save

docker run --rm -it -p 8080:8080 -v "$PWD/data:/var/opentripplanner" opentripplanner/opentripplanner:2.8.1 --load --serve
