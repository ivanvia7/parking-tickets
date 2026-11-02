from parking_tickets.portals import carto, socrata

# Each city file names its portal; both modules offer the same functions.
PORTALS = {"socrata": socrata, "carto": carto}
