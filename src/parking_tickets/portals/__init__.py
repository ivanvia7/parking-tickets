from parking_tickets.portals import arcgis, carto, socrata

# Each city file names its portal; every module offers the same functions.
PORTALS = {"socrata": socrata, "carto": carto, "arcgis": arcgis}
