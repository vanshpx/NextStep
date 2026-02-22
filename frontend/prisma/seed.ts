import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
    // Clean up existing data
    await prisma.activity.deleteMany();
    await prisma.day.deleteMany();
    await prisma.flight.deleteMany();
    await prisma.hotelStay.deleteMany();
    await prisma.itinerary.deleteMany();

    // ─── 1. Rahul Verma — Goa (Active) ─────────────────────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Rahul Verma',
            destination: 'Goa, India',
            dateRange: 'Feb 20 - Feb 24',
            status: 'Active',
            age: '28',
            days: '4',
            email: 'rahul.verma@email.com',
            mobile: '+91 98765 43210',
            origin: 'Mumbai',
            from: 'Mumbai',
            to: 'Goa',
            totalDays: 4,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: {
                create: [
                    {
                        type: 'Departure',
                        date: '2026-02-20',
                        airline: 'IndiGo',
                        flightNumber: '6E-302',
                        flightTime: '08:00',
                        arrivalTime: '09:30',
                        airport: 'Dabolim Airport, Goa',
                        lat: 15.3808,
                        lng: 73.8314,
                    },
                    {
                        type: 'Return',
                        date: '2026-02-24',
                        airline: 'Air India',
                        flightNumber: 'AI-854',
                        flightTime: '18:00',
                        arrivalTime: '19:30',
                        airport: 'Chhatrapati Shivaji Maharaj International Airport',
                        lat: 19.0896,
                        lng: 72.8656,
                    },
                ],
            },
            hotelStays: {
                create: [
                    {
                        hotelName: 'The Leela Goa',
                        checkIn: '2026-02-20',
                        checkOut: '2026-02-24',
                        notes: 'Beachfront resort, breakfast included',
                        lat: 15.0007,
                        lng: 74.0047,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '09:30', title: 'Arrival at Dabolim Airport', location: 'Dabolim Airport, Goa', notes: 'Flight: IndiGo 6E-302', status: 'completed', lat: 15.3808, lng: 73.8314, order: 0 },
                                { time: '10:00', title: 'Transfer to Hotel', location: 'The Leela Goa', notes: 'Private transfer arranged', status: 'completed', lat: 15.0007, lng: 74.0047, order: 1 },
                                { time: '13:00', title: 'Lunch at Fisherman\'s Wharf', location: 'Fisherman\'s Wharf, Cavelossim', notes: 'Seafood restaurant on the backwaters', status: 'completed', lat: 15.1701, lng: 73.9477, order: 2 },
                                { time: '16:00', title: 'Baga Beach Visit', location: 'Baga Beach, Goa', notes: 'Relax on the beach, sunset views', status: 'completed', lat: 15.5523, lng: 73.7513, order: 3 },
                                { time: '20:00', title: 'Dinner at Tito\'s Street', location: 'Tito\'s Lane, Baga', notes: 'Famous nightlife area', status: 'completed', lat: 15.5535, lng: 73.7513, order: 4 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Breakfast at Hotel', location: 'The Leela Goa', notes: 'Buffet breakfast', status: 'completed', lat: 15.0007, lng: 74.0047, order: 0 },
                                { time: '10:30', title: 'Old Goa Heritage Walk', location: 'Old Goa, Goa', notes: 'Visit Basilica of Bom Jesus & Se Cathedral', status: 'completed', lat: 15.5012, lng: 73.9116, order: 1 },
                                { time: '13:30', title: 'Lunch at Ritz Classic', location: 'Panaji, Goa', notes: 'Classic Goan cuisine', status: 'completed', lat: 15.4989, lng: 73.8278, order: 2 },
                                { time: '15:30', title: 'Anju Beach Resort & Spa', location: 'North Goa', status: 'upcoming', lat: 15.5535, lng: 73.7634, order: 3 },
                                { time: '19:00', title: 'Sunset Cruise on Mandovi River', location: 'Mandovi River, Panaji', notes: 'Live Goan folk music & dance', status: 'upcoming', lat: 15.5012, lng: 73.8274, order: 4 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '08:30', title: 'Dudhsagar Waterfall Trip', location: 'Dudhsagar Waterfall, Goa', notes: 'Full day excursion', status: 'upcoming', lat: 15.3137, lng: 74.3140, order: 0 },
                                { time: '13:00', title: 'Picnic Lunch near Waterfall', location: 'Bhagwan Mahavir Wildlife Sanctuary', status: 'upcoming', lat: 15.3147, lng: 74.3140, order: 1 },
                                { time: '18:00', title: 'Return to Hotel', location: 'The Leela Goa', status: 'upcoming', lat: 15.0007, lng: 74.0047, order: 2 },
                                { time: '20:30', title: 'Farewell Dinner', location: 'Beach Shack, South Goa', notes: 'Fresh catch of the day', status: 'upcoming', lat: 15.0008, lng: 74.0040, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Morning Beach Walk', location: 'Cavelossim Beach', status: 'upcoming', lat: 15.1701, lng: 73.9477, order: 0 },
                                { time: '11:00', title: 'Check-out & Shopping', location: 'The Leela Goa', notes: 'Pick up souvenirs from hotel boutique', status: 'upcoming', lat: 15.0007, lng: 74.0047, order: 1 },
                                { time: '14:00', title: 'Transfer to Airport', location: 'Dabolim Airport, Goa', status: 'upcoming', lat: 15.3808, lng: 73.8314, order: 2 },
                                { time: '18:00', title: 'Departure Flight to Mumbai', location: 'Dabolim Airport, Goa', notes: 'Air India AI-854', status: 'upcoming', lat: 15.3808, lng: 73.8314, order: 3 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    // ─── 2. Priya Sharma — Shimla + Manali (Upcoming) ──────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Priya Sharma',
            destination: 'Himachal Pradesh',
            dateRange: 'Mar 10 - Mar 15',
            status: 'Upcoming',
            age: '32',
            days: '5',
            email: 'priya.sharma@email.com',
            mobile: '+91 87654 32109',
            origin: 'Delhi',
            from: 'Delhi',
            to: 'Shimla',
            totalDays: 5,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: {
                create: [
                    {
                        type: 'Departure',
                        date: '2026-03-10',
                        airline: 'SpiceJet',
                        flightNumber: 'SG-113',
                        flightTime: '07:00',
                        arrivalTime: '08:00',
                        airport: 'Jubbarhatti Airport, Shimla',
                        lat: 31.0827,
                        lng: 77.0672,
                    },
                    {
                        type: 'Return',
                        date: '2026-03-15',
                        airline: 'SpiceJet',
                        flightNumber: 'SG-114',
                        flightTime: '17:00',
                        arrivalTime: '18:00',
                        airport: 'Indira Gandhi International Airport, Delhi',
                        lat: 28.5562,
                        lng: 77.0999,
                    },
                ],
            },
            hotelStays: {
                create: [
                    {
                        hotelName: 'Wildflower Hall, Shimla',
                        checkIn: '2026-03-10',
                        checkOut: '2026-03-13',
                        notes: 'Mountain resort with scenic views',
                        lat: 31.1048,
                        lng: 77.0826,
                    },
                    {
                        hotelName: 'The Himalayan, Manali',
                        checkIn: '2026-03-13',
                        checkOut: '2026-03-15',
                        notes: 'Luxury boutique hotel',
                        lat: 32.2396,
                        lng: 77.1887,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '08:00', title: 'Arrival at Shimla Airport', location: 'Jubbarhatti Airport, Shimla', notes: 'Flight: SpiceJet SG-113', status: 'upcoming', lat: 31.0827, lng: 77.0672, order: 0 },
                                { time: '09:30', title: 'Transfer to Hotel', location: 'Wildflower Hall, Shimla', status: 'upcoming', lat: 31.1048, lng: 77.0826, order: 1 },
                                { time: '14:00', title: 'Mall Road Stroll', location: 'Mall Road, Shimla', notes: 'Shopping and sightseeing', status: 'upcoming', lat: 31.1048, lng: 77.1734, order: 2 },
                                { time: '17:00', title: 'Visit Christ Church', location: 'Christ Church, Shimla', notes: 'Colonial era church with stunning views', status: 'upcoming', lat: 31.1041, lng: 77.1714, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Kufri Adventure Day', location: 'Kufri, Shimla', notes: 'Snow activities and yak rides', status: 'upcoming', lat: 31.0986, lng: 77.2682, order: 0 },
                                { time: '13:00', title: 'Lunch at Café Sol', location: 'Kufri, Shimla', status: 'upcoming', lat: 31.0986, lng: 77.2680, order: 1 },
                                { time: '16:00', title: 'Jakhu Temple Visit', location: 'Jakhu Hill, Shimla', notes: 'Ancient Hanuman temple with city views', status: 'upcoming', lat: 31.1054, lng: 77.1826, order: 2 },
                                { time: '19:00', title: 'Dinner at Oberoi Cecil', location: 'Shimla, Himachal Pradesh', status: 'upcoming', lat: 31.1041, lng: 77.1770, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '07:00', title: 'Drive to Manali', location: 'Shimla → Manali Highway', notes: '7-8 hour scenic mountain drive', status: 'upcoming', lat: 31.1048, lng: 77.0826, order: 0 },
                                { time: '15:00', title: 'Arrival at The Himalayan', location: 'The Himalayan, Manali', status: 'upcoming', lat: 32.2396, lng: 77.1887, order: 1 },
                                { time: '18:00', title: 'Mall Road Manali', location: 'Mall Road, Manali', status: 'upcoming', lat: 32.2396, lng: 77.1897, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Solang Valley Excursion', location: 'Solang Valley, Manali', notes: 'Paragliding & Zorbing', status: 'upcoming', lat: 32.3217, lng: 77.1493, order: 0 },
                                { time: '13:30', title: 'Lunch at Johnson\'s Café', location: 'Johnson\'s Hotel, Manali', status: 'upcoming', lat: 32.2396, lng: 77.1880, order: 1 },
                                { time: '16:00', title: 'Hadimba Devi Temple', location: 'Dhungri, Manali', notes: '16th century temple in cedar forest', status: 'upcoming', lat: 32.2303, lng: 77.1888, order: 2 },
                                { time: '19:00', title: 'River Beas Evening Walk', location: 'Beas River, Manali', status: 'upcoming', lat: 32.2396, lng: 77.1890, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 5,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Morning Spa', location: 'The Himalayan, Manali', notes: 'Traditional Himalayan treatments', status: 'upcoming', lat: 32.2396, lng: 77.1887, order: 0 },
                                { time: '11:00', title: 'Check-out', location: 'The Himalayan, Manali', status: 'upcoming', lat: 32.2396, lng: 77.1887, order: 1 },
                                { time: '13:00', title: 'Drive to Airport', location: 'Jubbarhatti Airport, Shimla', status: 'upcoming', lat: 31.0827, lng: 77.0672, order: 2 },
                                { time: '17:00', title: 'Departure to Delhi', location: 'Jubbarhatti Airport, Shimla', notes: 'SpiceJet SG-114', status: 'upcoming', lat: 31.0827, lng: 77.0672, order: 3 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    // ─── 3. Arjun Mehta — Kerala (Draft) ────────────────────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Arjun Mehta',
            destination: 'Kerala, India',
            dateRange: 'Apr 5 - Apr 12',
            status: 'Draft',
            age: '45',
            days: '7',
            email: 'arjun.mehta@email.com',
            mobile: '+91 76543 21098',
            origin: 'Bangalore',
            from: 'Bangalore',
            to: 'Kochi',
            totalDays: 7,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: {
                create: [
                    {
                        type: 'Departure',
                        date: '2026-04-05',
                        airline: 'Vistara',
                        flightNumber: 'UK-805',
                        flightTime: '10:00',
                        arrivalTime: '11:30',
                        airport: 'Cochin International Airport',
                        lat: 10.1520,
                        lng: 76.3919,
                    },
                    {
                        type: 'Return',
                        date: '2026-04-12',
                        airline: 'Vistara',
                        flightNumber: 'UK-806',
                        flightTime: '16:00',
                        arrivalTime: '17:30',
                        airport: 'Kempegowda International Airport, Bangalore',
                        lat: 13.1986,
                        lng: 77.7066,
                    },
                ],
            },
            hotelStays: {
                create: [
                    {
                        hotelName: 'Taj Malabar Resort, Kochi',
                        checkIn: '2026-04-05',
                        checkOut: '2026-04-08',
                        notes: 'Heritage waterfront hotel',
                        lat: 9.9659,
                        lng: 76.2673,
                    },
                    {
                        hotelName: 'Taj Kumarakom Resort',
                        checkIn: '2026-04-08',
                        checkOut: '2026-04-12',
                        notes: 'Backwater luxury resort',
                        lat: 9.5988,
                        lng: 76.4389,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '11:30', title: 'Arrival at Cochin Airport', location: 'Cochin International Airport', notes: 'Flight: Vistara UK-805', status: 'upcoming', lat: 10.1520, lng: 76.3919, order: 0 },
                                { time: '13:00', title: 'Transfer to Hotel', location: 'Taj Malabar Resort, Kochi', status: 'upcoming', lat: 9.9659, lng: 76.2673, order: 1 },
                                { time: '16:00', title: 'Fort Kochi Walk', location: 'Fort Kochi, Kerala', notes: 'Colonial heritage & Chinese fishing nets', status: 'upcoming', lat: 9.9648, lng: 76.2428, order: 2 },
                                { time: '19:00', title: 'Kerala Cuisine Dinner', location: 'Old Harbour Hotel, Kochi', status: 'upcoming', lat: 9.9622, lng: 76.2434, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Kathakali Performance', location: 'Kerala Kathakali Centre, Kochi', notes: 'Traditional dance form', status: 'upcoming', lat: 9.9648, lng: 76.2450, order: 0 },
                                { time: '13:00', title: 'Mattancherry Spice Market', location: 'Mattancherry, Kochi', status: 'upcoming', lat: 9.9588, lng: 76.2580, order: 1 },
                                { time: '16:00', title: 'Jewish Synagogue Visit', location: 'Paradesi Synagogue, Mattancherry', notes: 'Oldest active synagogue in India', status: 'upcoming', lat: 9.9572, lng: 76.2600, order: 2 },
                                { time: '20:00', title: 'Sunset Cruise', location: 'Kochi Backwaters', status: 'upcoming', lat: 9.9659, lng: 76.2673, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Drive to Munnar', location: 'Munnar, Kerala', notes: '3 hour scenic drive through tea estates', status: 'upcoming', lat: 10.0889, lng: 77.0595, order: 0 },
                                { time: '13:00', title: 'Tea Museum Visit', location: 'Tea Museum, Munnar', status: 'upcoming', lat: 10.0889, lng: 77.0600, order: 1 },
                                { time: '15:00', title: 'Eravikulam National Park', location: 'Eravikulam, Munnar', notes: 'Nilgiri Tahr spotting', status: 'upcoming', lat: 10.1718, lng: 77.0534, order: 2 },
                                { time: '19:00', title: 'Return to Kochi Hotel', location: 'Taj Malabar Resort, Kochi', status: 'upcoming', lat: 9.9659, lng: 76.2673, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Check-out & Drive to Alleppey', location: 'Alleppey, Kerala', notes: 'Backwater capital of Kerala', status: 'upcoming', lat: 9.4981, lng: 76.3388, order: 0 },
                                { time: '12:00', title: 'Houseboat Check-in', location: 'Alleppey Backwaters', notes: 'Luxury overnight houseboat', status: 'upcoming', lat: 9.4981, lng: 76.3388, order: 1 },
                                { time: '15:00', title: 'Backwater Cruise', location: 'Vembanad Lake, Kerala', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 2 },
                                { time: '19:00', title: 'Dinner on Houseboat', location: 'Vembanad Lake, Kerala', notes: 'Fresh seafood and Kerala cuisine', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 5,
                        activities: {
                            create: [
                                { time: '07:00', title: 'Sunrise on Backwaters', location: 'Vembanad Lake, Kerala', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 0 },
                                { time: '10:00', title: 'Houseboat Check-out & Transfer', location: 'Kumarakom, Kerala', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 1 },
                                { time: '12:00', title: 'Check-in Taj Kumarakom', location: 'Taj Kumarakom Resort', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 2 },
                                { time: '15:00', title: 'Kumarakom Bird Sanctuary', location: 'Kumarakom Bird Sanctuary', notes: 'Migratory birds watching', status: 'upcoming', lat: 9.6137, lng: 76.4372, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 6,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Ayurvedic Spa Treatment', location: 'Taj Kumarakom Resort', notes: 'Traditional Kerala Massage', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 0 },
                                { time: '12:00', title: 'Kottayam City Visit', location: 'Kottayam, Kerala', notes: 'Land of letters, rubber and fish', status: 'upcoming', lat: 9.5916, lng: 76.5222, order: 1 },
                                { time: '16:00', title: 'St. Mary\'s Church', location: 'Ettumanoor, Kerala', notes: 'Famous temple festival', status: 'upcoming', lat: 9.6777, lng: 76.5556, order: 2 },
                                { time: '20:00', title: 'Farewell Dinner', location: 'Naj Kumarakom, Kerala', notes: 'Special Kerala Sadya', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 7,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Morning Yoga & Meditation', location: 'Taj Kumarakom Resort', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 0 },
                                { time: '11:00', title: 'Check-out', location: 'Taj Kumarakom Resort', status: 'upcoming', lat: 9.5988, lng: 76.4389, order: 1 },
                                { time: '13:00', title: 'Transfer to Cochin Airport', location: 'Cochin International Airport', status: 'upcoming', lat: 10.1520, lng: 76.3919, order: 2 },
                                { time: '16:00', title: 'Departure to Bangalore', location: 'Cochin International Airport', notes: 'Vistara UK-806', status: 'upcoming', lat: 10.1520, lng: 76.3919, order: 3 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    console.log('✅ Seed complete — 3 itineraries created (Active, Upcoming, Draft)');

    // ─── 4. Amit Patel — Rajasthan (Upcoming) ──────────────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Amit Patel',
            destination: 'Rajasthan, India',
            dateRange: 'Mar 20 - Mar 27',
            status: 'Upcoming',
            age: '35',
            days: '7',
            email: 'amit.patel@email.com',
            mobile: '+91 95678 12345',
            origin: 'Mumbai',
            from: 'Mumbai',
            to: 'Jaipur',
            totalDays: 7,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: {
                create: [
                    {
                        type: 'Departure',
                        date: '2026-03-20',
                        airline: 'Air India',
                        flightNumber: 'AI-472',
                        flightTime: '09:00',
                        arrivalTime: '10:30',
                        airport: 'Jaipur International Airport',
                        lat: 26.8242,
                        lng: 75.8122,
                    },
                    {
                        type: 'Return',
                        date: '2026-03-27',
                        airline: 'Air India',
                        flightNumber: 'AI-473',
                        flightTime: '17:00',
                        arrivalTime: '18:30',
                        airport: 'Chhatrapati Shivaji Maharaj International Airport',
                        lat: 19.0896,
                        lng: 72.8656,
                    },
                ],
            },
            hotelStays: {
                create: [
                    {
                        hotelName: 'Rambagh Palace, Jaipur',
                        checkIn: '2026-03-20',
                        checkOut: '2026-03-24',
                        notes: 'Former royal palace, heritage property',
                        lat: 26.8975,
                        lng: 75.8151,
                    },
                    {
                        hotelName: 'Umaid Bhawan Palace, Jodhpur',
                        checkIn: '2026-03-24',
                        checkOut: '2026-03-27',
                        notes: 'Luxury heritage palace hotel',
                        lat: 26.2965,
                        lng: 73.0387,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '10:30', title: 'Arrival at Jaipur Airport', location: 'Jaipur International Airport', notes: 'Air India AI-472', status: 'upcoming', lat: 26.8242, lng: 75.8122, order: 0 },
                                { time: '12:00', title: 'Check-in Rambagh Palace', location: 'Rambagh Palace, Jaipur', status: 'upcoming', lat: 26.8975, lng: 75.8151, order: 1 },
                                { time: '15:00', title: 'City Palace Visit', location: 'City Palace, Jaipur', notes: 'Royal family museum and palace complex', status: 'upcoming', lat: 26.9258, lng: 75.8237, order: 2 },
                                { time: '18:00', title: 'Hawa Mahal Sunset View', location: 'Hawa Mahal, Jaipur', notes: 'Palace of Winds at golden hour', status: 'upcoming', lat: 26.9239, lng: 75.8267, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Amber Fort Elephant Ride', location: 'Amber Fort, Jaipur', notes: 'UNESCO World Heritage Site', status: 'upcoming', lat: 26.9855, lng: 75.8513, order: 0 },
                                { time: '13:00', title: 'Lunch at Suvarna Mahal', location: 'Rambagh Palace, Jaipur', notes: 'Royal Rajasthani cuisine', status: 'upcoming', lat: 26.8975, lng: 75.8151, order: 1 },
                                { time: '15:30', title: 'Jantar Mantar Observatory', location: 'Jantar Mantar, Jaipur', status: 'upcoming', lat: 26.9248, lng: 75.8242, order: 2 },
                                { time: '19:00', title: 'Chokhi Dhani Village Experience', location: 'Chokhi Dhani, Jaipur', notes: 'Traditional Rajasthani dinner & folk performance', status: 'upcoming', lat: 26.7733, lng: 75.8697, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Drive to Pushkar', location: 'Pushkar, Rajasthan', notes: '2 hour scenic drive', status: 'upcoming', lat: 26.4900, lng: 74.5510, order: 0 },
                                { time: '11:30', title: 'Brahma Temple Visit', location: 'Brahma Temple, Pushkar', notes: 'One of the few Brahma temples in India', status: 'upcoming', lat: 26.4892, lng: 74.5501, order: 1 },
                                { time: '13:00', title: 'Lunch at Sunset Café', location: 'Pushkar Lake', status: 'upcoming', lat: 26.4893, lng: 74.5518, order: 2 },
                                { time: '16:00', title: 'Pushkar Lake Boat Ride', location: 'Pushkar Lake', status: 'upcoming', lat: 26.4893, lng: 74.5518, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '08:00', title: 'Drive to Jodhpur', location: 'Jodhpur, Rajasthan', notes: 'Blue City of India, 3 hour drive', status: 'upcoming', lat: 26.2389, lng: 73.0243, order: 0 },
                                { time: '12:00', title: 'Check-in Umaid Bhawan Palace', location: 'Umaid Bhawan Palace, Jodhpur', status: 'upcoming', lat: 26.2965, lng: 73.0387, order: 1 },
                                { time: '15:00', title: 'Mehrangarh Fort', location: 'Mehrangarh Fort, Jodhpur', notes: 'Majestic fort overlooking the blue city', status: 'upcoming', lat: 26.2980, lng: 73.0188, order: 2 },
                                { time: '19:00', title: 'Dinner at Pillars', location: 'Umaid Bhawan Palace, Jodhpur', notes: 'Fine dining with palace views', status: 'upcoming', lat: 26.2965, lng: 73.0387, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 5,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Jaswant Thada Memorial', location: 'Jodhpur, Rajasthan', notes: 'Marble cenotaph of Maharaja Jaswant Singh II', status: 'upcoming', lat: 26.2981, lng: 73.0212, order: 0 },
                                { time: '11:00', title: 'Clock Tower Spice Market', location: 'Sardar Market, Jodhpur', notes: 'Famous spice and handicraft bazaar', status: 'upcoming', lat: 26.2944, lng: 73.0177, order: 1 },
                                { time: '15:00', title: 'Drive to Jaisalmer', location: 'Jaisalmer, Rajasthan', notes: 'The Golden City, 5 hour drive', status: 'upcoming', lat: 26.9157, lng: 70.9083, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 6,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Jaisalmer Fort', location: 'Jaisalmer Fort, Rajasthan', notes: 'Living fort, UNESCO site', status: 'upcoming', lat: 26.9124, lng: 70.9129, order: 0 },
                                { time: '13:00', title: 'Patwon Ki Haveli', location: 'Jaisalmer, Rajasthan', notes: 'Cluster of 5 havelis', status: 'upcoming', lat: 26.9127, lng: 70.9134, order: 1 },
                                { time: '16:00', title: 'Sam Sand Dunes Camel Safari', location: 'Sam Sand Dunes, Jaisalmer', notes: 'Sunset camel ride & desert camping', status: 'upcoming', lat: 26.8831, lng: 70.5715, order: 2 },
                                { time: '20:00', title: 'Desert Cultural Program', location: 'Sam Sand Dunes Camp', notes: 'Folk music & dinner under stars', status: 'upcoming', lat: 26.8831, lng: 70.5715, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 7,
                        activities: {
                            create: [
                                { time: '08:00', title: 'Morning in Golden City', location: 'Jaisalmer, Rajasthan', status: 'upcoming', lat: 26.9157, lng: 70.9083, order: 0 },
                                { time: '12:00', title: 'Drive to Jodhpur Airport', location: 'Jodhpur Airport', notes: '5 hour drive', status: 'upcoming', lat: 26.2510, lng: 73.0489, order: 1 },
                                { time: '17:00', title: 'Departure to Mumbai', location: 'Jodhpur Airport', notes: 'Air India AI-473', status: 'upcoming', lat: 26.2510, lng: 73.0489, order: 2 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    // ─── 5. Anjali Mehta — Coorg, Karnataka (Draft) ─────────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Anjali Mehta',
            destination: 'Coorg, Karnataka',
            dateRange: 'Apr 15 - Apr 19',
            status: 'Draft',
            age: '29',
            days: '4',
            email: 'anjali.mehta@email.com',
            mobile: '+91 94567 89012',
            origin: 'Bangalore',
            from: 'Bangalore',
            to: 'Coorg',
            totalDays: 4,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: { create: [] },
            hotelStays: {
                create: [
                    {
                        hotelName: 'Taj Madikeri Resort & Spa, Coorg',
                        checkIn: '2026-04-15',
                        checkOut: '2026-04-19',
                        notes: 'Luxury jungle resort with spa',
                        lat: 12.4161,
                        lng: 75.7329,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Drive from Bangalore to Coorg', location: 'Bangalore → Coorg', notes: '5 hour scenic drive through coffee estates', status: 'upcoming', lat: 12.4161, lng: 75.7329, order: 0 },
                                { time: '16:00', title: 'Check-in Taj Madikeri', location: 'Taj Madikeri Resort, Coorg', status: 'upcoming', lat: 12.4161, lng: 75.7329, order: 1 },
                                { time: '18:00', title: 'Abbey Falls at Sunset', location: 'Abbey Falls, Coorg', notes: 'Beautiful waterfall surrounded by coffee plantations', status: 'upcoming', lat: 12.4176, lng: 75.7242, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '08:00', title: 'Coffee Plantation Walk', location: 'Coorg Coffee Estate', notes: 'Learn about coffee processing', status: 'upcoming', lat: 12.4161, lng: 75.7329, order: 0 },
                                { time: '11:00', title: 'Dubare Elephant Camp', location: 'Dubare, Coorg', notes: 'Bathe and feed elephants', status: 'upcoming', lat: 12.3741, lng: 75.8564, order: 1 },
                                { time: '14:00', title: 'Cauvery Nisargadhama', location: 'Kushalanagar, Coorg', notes: 'Island nature park on Cauvery river', status: 'upcoming', lat: 12.4617, lng: 75.9668, order: 2 },
                                { time: '19:00', title: 'Candlelit Dinner', location: 'Taj Madikeri, Coorg', notes: 'Coorgi local delicacies', status: 'upcoming', lat: 12.4161, lng: 75.7329, order: 3 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Talacauvery – Source of Cauvery', location: 'Brahmagiri, Coorg', notes: 'Sacred hilltop, source of river Cauvery', status: 'upcoming', lat: 11.9619, lng: 75.5614, order: 0 },
                                { time: '13:00', title: 'Bhagamandala Temple', location: 'Bhagamandala, Coorg', notes: 'Confluence of rivers Cauvery, Kaveri, Sujyothi', status: 'upcoming', lat: 11.9741, lng: 75.5660, order: 1 },
                                { time: '16:00', title: 'Namdroling Monastery', location: 'Bylakuppe, Coorg', notes: 'Golden Temple — largest Buddhist monastery in India', status: 'upcoming', lat: 12.1890, lng: 75.9770, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Spa Morning', location: 'Taj Madikeri, Coorg', notes: 'Coorg Kodo traditional massage', status: 'upcoming', lat: 12.4161, lng: 75.7329, order: 0 },
                                { time: '11:00', title: 'Check-out & Drive to Bangalore', location: 'Bangalore', status: 'upcoming', lat: 12.9716, lng: 77.5946, order: 1 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    // ─── 6. Sarah Jenkins — Dubai (Completed) ────────────────────────────────────
    await prisma.itinerary.create({
        data: {
            client: 'Sarah Jenkins',
            destination: 'Dubai, UAE',
            dateRange: 'Jan 10 - Jan 17',
            status: 'Completed',
            age: '34',
            days: '7',
            email: 'sarah.jenkins@email.com',
            mobile: '+44 7700 900123',
            origin: 'London',
            from: 'London',
            to: 'Dubai',
            totalDays: 7,
            agentName: 'Aman Sharma',
            agentPhone: '+91 91234 56789',
            flights: {
                create: [
                    {
                        type: 'Departure',
                        date: '2026-01-10',
                        airline: 'Emirates',
                        flightNumber: 'EK-003',
                        flightTime: '21:30',
                        arrivalTime: '07:45',
                        airport: 'Dubai International Airport',
                        lat: 25.2532,
                        lng: 55.3657,
                    },
                    {
                        type: 'Return',
                        date: '2026-01-17',
                        airline: 'Emirates',
                        flightNumber: 'EK-004',
                        flightTime: '10:30',
                        arrivalTime: '14:15',
                        airport: 'Heathrow Airport, London',
                        lat: 51.4700,
                        lng: -0.4543,
                    },
                ],
            },
            hotelStays: {
                create: [
                    {
                        hotelName: 'Burj Al Arab Jumeirah',
                        checkIn: '2026-01-10',
                        checkOut: '2026-01-17',
                        notes: 'Iconic sail-shaped luxury hotel',
                        lat: 25.1412,
                        lng: 55.1853,
                    },
                ],
            },
            itineraryDays: {
                create: [
                    {
                        dayNumber: 1,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Arrival & Hotel Check-in', location: 'Burj Al Arab Jumeirah, Dubai', notes: 'Emirates EK-003', status: 'completed', lat: 25.1412, lng: 55.1853, order: 0 },
                                { time: '14:00', title: 'Dubai Mall & Burj Khalifa', location: 'Downtown Dubai', notes: 'World\'s tallest building — observation deck', status: 'completed', lat: 25.1972, lng: 55.2744, order: 1 },
                                { time: '19:30', title: 'Dubai Fountain Show', location: 'Dubai Fountain, Downtown', notes: 'World\'s largest choreographed fountain', status: 'completed', lat: 25.1951, lng: 55.2796, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 2,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Desert Safari', location: 'Dubai Desert Conservation Reserve', notes: 'Dune bashing & camel ride', status: 'completed', lat: 24.8925, lng: 55.5286, order: 0 },
                                { time: '19:00', title: 'Bedouin Camp Dinner', location: 'Dubai Desert', notes: 'Traditional Arabic dinner & belly dancing', status: 'completed', lat: 24.8925, lng: 55.5286, order: 1 },
                            ],
                        },
                    },
                    {
                        dayNumber: 3,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Gold & Spice Souks', location: 'Deira, Dubai', notes: 'Traditional Dubai markets', status: 'completed', lat: 25.2697, lng: 55.3094, order: 0 },
                                { time: '14:00', title: 'Dubai Creek Abra Ride', location: 'Dubai Creek', notes: 'Traditional wooden boat across the creek', status: 'completed', lat: 25.2631, lng: 55.2972, order: 1 },
                                { time: '17:00', title: 'Al Fahidi Historic District', location: 'Al Fahidi, Dubai', notes: 'Old Dubai heritage quarter', status: 'completed', lat: 25.2632, lng: 55.2972, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 4,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Palm Jumeirah Tour', location: 'Palm Jumeirah, Dubai', notes: 'Iconic man-made island', status: 'completed', lat: 25.1124, lng: 55.1390, order: 0 },
                                { time: '14:00', title: 'Aquaventure Waterpark', location: 'Atlantis The Palm', notes: 'Water slides & private beach', status: 'completed', lat: 25.1302, lng: 55.1169, order: 1 },
                                { time: '20:00', title: 'Dinner at Nobu Dubai', location: 'Atlantis The Palm', notes: 'World-class Japanese-Peruvian cuisine', status: 'completed', lat: 25.1302, lng: 55.1169, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 5,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Dubai Frame', location: 'Zabeel Park, Dubai', notes: 'World\'s largest picture frame with panoramic views', status: 'completed', lat: 25.2347, lng: 55.3001, order: 0 },
                                { time: '14:00', title: 'Global Village', location: 'Global Village, Dubai', notes: 'Cultural fair from 90 countries', status: 'completed', lat: 25.0691, lng: 55.3049, order: 1 },
                                { time: '19:00', title: 'Sky Views Observatory', location: 'Address Downtown Dubai', notes: 'Glass slide 220m above ground', status: 'completed', lat: 25.1922, lng: 55.2778, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 6,
                        activities: {
                            create: [
                                { time: '10:00', title: 'Miracle Garden', location: 'Al Barsha, Dubai', notes: 'World\'s largest natural flower garden', status: 'completed', lat: 25.0631, lng: 55.2380, order: 0 },
                                { time: '14:00', title: 'Mall of the Emirates – Ski Dubai', location: 'Mall of the Emirates', notes: 'Indoor ski slope at 22°C outside!', status: 'completed', lat: 25.1182, lng: 55.2003, order: 1 },
                                { time: '20:00', title: 'Farewell Dinner — 360° Restaurant', location: 'Jumeirah Beach Hotel', notes: 'Rotating rooftop restaurant', status: 'completed', lat: 25.1421, lng: 55.1899, order: 2 },
                            ],
                        },
                    },
                    {
                        dayNumber: 7,
                        activities: {
                            create: [
                                { time: '09:00', title: 'Morning Brunch', location: 'Burj Al Arab, Dubai', status: 'completed', lat: 25.1412, lng: 55.1853, order: 0 },
                                { time: '11:00', title: 'Check-out', location: 'Burj Al Arab Jumeirah', status: 'completed', lat: 25.1412, lng: 55.1853, order: 1 },
                                { time: '14:00', title: 'Last-minute Shopping', location: 'Dubai Duty Free', status: 'completed', lat: 25.2532, lng: 55.3657, order: 2 },
                                { time: '10:30', title: 'Departure to London', location: 'Dubai International Airport', notes: 'Emirates EK-004', status: 'completed', lat: 25.2532, lng: 55.3657, order: 3 },
                            ],
                        },
                    },
                ],
            },
        },
    });

    console.log('✅ Seed complete — 6 itineraries created (Active, 2× Upcoming, 2× Draft, Completed)');
}

main()
    .catch(e => {
        console.error(e);
        process.exit(1);
    })
    .finally(() => prisma.$disconnect());
