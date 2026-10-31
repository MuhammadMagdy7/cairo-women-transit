# GTFS Data Profile — Greater Cairo 2025

| table | rows | columns | columns with nulls |
|---|---:|---|---|
| agency | 11 | agency_id, agency_name, agency_url, agency_timezone | — |
| calendar | 2 | monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date, service_id | — |
| feed_info | 1 | feed_publisher_name, feed_publisher_url, feed_start_date, feed_end_date, feed_version, feed_lang | — |
| frequencies | 6,432 | trip_id, start_time, end_time, headway_secs | — |
| routes | 1,011 | route_id, agency_id, route_long_name, route_short_name, route_type, continuous_pickup, continuous_drop_off | — |
| shapes | 531,958 | shape_id, shape_pt_sequence, shape_pt_lat, shape_pt_lon | — |
| stop_times | 44,743 | trip_id, stop_id, stop_sequence, arrival_time, departure_time | — |
| stops | 2,997 | stop_id, stop_name, stop_lat, stop_lon | — |
| translations | 3,106 | table_name, field_name, language, field_value, translation | — |
| trips | 1,784 | route_id, service_id, trip_headsign, direction_id, shape_id, trip_id | — |

## Primary-key duplicates
- agency ['agency_id']: 0
- routes ['route_id']: 0
- stops ['stop_id']: 0
- trips ['trip_id']: 0
- calendar ['service_id']: 0
- stop_times ['trip_id', 'stop_sequence']: 0
- frequencies ['trip_id', 'start_time']: 0
- shapes ['shape_id', 'shape_pt_sequence']: 0

## Foreign-key orphans (child rows with no parent)
- routes.agency_id → agency.agency_id: 0
- trips.route_id → routes.route_id: 0
- trips.service_id → calendar.service_id: 0
- trips.shape_id → shapes.shape_id: 0
- stop_times.trip_id → trips.trip_id: 0
- stop_times.stop_id → stops.stop_id: 0
- frequencies.trip_id → trips.trip_id: 0

## Coverage
- routes without trips: 0
- trips without stop_times: 0
- trips without frequencies: 28
- stops never served: 67

## Agencies (routes per operator)
- Paratransit 14 Seater Microbus (Orange Licenseplates): 511
- Cairo Transport Authority: 244
- Minibus licensed by CTA: 107
- Paratransit 8 Seater Suzuki Chevrolet or DMF (Blue Licenseplates): 70
- Cooperative paratransit 29 Seater (Grey Licenseplates): 49
- Mwasalat Misr: 18
- Box Paratransit: 9
- Green Bus: 2
- Minibus licensed by LTRA: 1

## Value checks
- stop_lat range: 29.7447 – 30.2951
- stop_lon range: 30.8771 – 31.7554
- route_type values: ['3']
- headway (min): min 0.8, median 15.0, max 120.0
- frequency windows: ['06:00:00', '10:00:00', '15:00:00', '19:00:00']
- stop_times with hour ≥ 24: 0
- max stop_name length: 72
- max route_long_name length: 82
- translation tables/fields: {('agency', 'agency_name'): 11, ('routes', 'route_long_name'): 885, ('routes', 'route_short_name'): 358, ('stops', 'stop_name'): 1572, ('trips', 'trip_headsign'): 280}
- translations languages: ['ar']