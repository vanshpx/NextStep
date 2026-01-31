from backend.google_places_client import text_search, place_details


def get_places_for_destination(destination: str):
    """
    Google Places ONLY.
    Focused on landmarks, attractions, public places, and food.
    """

    queries = [
        f"most famous landmarks in {destination}",
        f"top tourist attractions in {destination}",
        f"iconic public places in {destination}",
        f"famous local restaurants in {destination}",
        f"popular cafes in {destination}"
    ]

    all_places = []

    for query in queries:
        results = text_search(query, max_results=5)

        for r in results:
            details = place_details(r["place_id"])
            if not details:
                continue

            all_places.append(details)

    # Deduplicate by name
    unique = {}
    for p in all_places:
        unique[p["name"]] = p

    return list(unique.values())
