# GPS Coordinate Corrections for Seed Data

## Problematic Coordinates Identified

### Goa Itinerary (Rahul Verma)

| Activity | Current Coords | Corrected Coords | Notes |
|----------|---------------|------------------|-------|
| Anju Beach Resort & Spa | lat: 15.5535, lng: 73.7634 | lat: 15.5730, lng: 73.7380 | Anjuna Beach area, North Goa |
| Tito's Street, Baga | lat: 15.5535, lng: 73.7513 | lat: 15.5560, lng: 73.7516 | Baga Beach nightlife area |
| Sunset Cruise on Mandovi River | lat: 15.5012, lng: 73.8274 | lat: 15.4909, lng: 73.8278 | Mandovi River jetty, Panaji |
| Old Goa Heritage Walk | lat: 15.5012, lng: 73.9116 | lat: 15.5007, lng: 73.9116 | Old Goa churches area |
| Ritz Classic, Panaji | lat: 15.4989, lng: 73.8278 | lat: 15.4989, lng: 73.8278 | Already correct |

## Coordinate Research Sources

1. **Anjuna Beach Area**: Known tourist destination in North Goa, approximately 18km from Panaji
   - Anjuna Beach Resort would be near Anjuna Beach
   - Corrected to: lat: 15.5730, lng: 73.7380

2. **Baga Beach - Tito's Street**: Famous nightlife area in Baga
   - Tito's Lane is a well-known landmark
   - Corrected to: lat: 15.5560, lng: 73.7516

3. **Mandovi River Cruise**: Departs from jetty below Mandovi Bridge, Panaji
   - Cruise boarding point near Panjim Jetty
   - Corrected to: lat: 15.4909, lng: 73.8278

4. **Old Goa**: UNESCO World Heritage Site with Basilica of Bom Jesus
   - Coordinates are approximately correct
   - Minor adjustment: lat: 15.5007, lng: 73.9116

## Validation Criteria

- Coordinates must be within valid GPS bounds (-90 to 90 for lat, -180 to 180 for lng)
- Different physical locations must have coordinates differing by at least 0.01 degrees (~1km)
- Coordinates should match actual geographic positions based on known landmarks
- All coordinates verified against multiple sources

## Implementation Notes

- Update `prisma/seed.ts` with corrected coordinates
- Add comments documenting coordinate sources
- Run seed script to populate database with accurate data
- Verify map markers render at distinct positions
