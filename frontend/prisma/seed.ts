import { PrismaClient } from '@prisma/client';
import { computeActivityOrder } from '../src/lib/sortActivities';

const prisma = new PrismaClient();

const itineraries = [
    {
        client: "Rahul Verma",
        destination: "Ahmedabad, Gujarat",
        status: "Active",
        dateRange: "Feb 10 - Feb 12",
        age: 28,
        days: 3,
        email: "rahul.verma@example.com",
        mobile: "+91 98765 43210",
        origin: "Mumbai",
        from: "Mumbai",
        to: "Ahmedabad",
        totalDays: 3,
        flights: {
            create: [
                { type: "Departure", date: "2024-02-10", airport: "BOM", airline: "IndiGo", flightNumber: "6E-123", flightTime: "08:00", arrivalTime: "09:15", lat: 19.0886, lng: 72.8687 },
                { type: "Return", date: "2024-02-12", airport: "AMD", airline: "Air India", flightNumber: "AI-456", flightTime: "17:00", arrivalTime: "18:15", lat: 23.0734, lng: 72.6266 }
            ]
        },
        hotelStays: {
            create: [
                { hotelName: "Hyatt Regency", checkIn: "2024-02-10", checkOut: "2024-02-12", notes: "River view room requested", lat: 23.0423, lng: 72.5744 }
            ]
        },
        itineraryDays: {
            create: [
                {
                    dayNumber: 1,
                    activities: {
                        create: [
                            { time: "10:00", title: "Arrival at AMD Airport", location: "Sardar Vallabhbhai Patel Airport", notes: "Cab booked - GJ-01-AB-1234", status: "completed", lat: 23.0734, lng: 72.6266 },
                            { time: "13:00", title: "Check-in: Hyatt Regency", location: "Ashram Road", notes: "River view room requested", status: "current", lat: 23.0423, lng: 72.5744 },
                            { time: "16:00", title: "Sabarmati Ashram", location: "Gandhi Ashram", notes: "Guided tour starts at 4:15 PM", status: "upcoming", lat: 23.0605, lng: 72.5808 },
                            { time: "19:00", title: "Riverfront Walk", location: "Sabarmati Riverfront", notes: "Evening leisure walk", status: "upcoming", lat: 23.0336, lng: 72.5707 }
                        ]
                    }
                },
                {
                    dayNumber: 2,
                    activities: {
                        create: [
                            { time: "09:00", title: "Adalaj Stepwell", location: "Adalaj", notes: "Architectural tour", status: "upcoming", lat: 23.1667, lng: 72.5801 },
                            { time: "12:00", title: "Akshardham Temple", location: "Gandhinagar", notes: "No electronics allowed inside", status: "upcoming", lat: 23.2285, lng: 72.6741 },
                            { time: "16:00", title: "Science City", location: "Hebatpur", notes: "Aquatics gallery tickets included", status: "upcoming", lat: 23.0772, lng: 72.4939 }
                        ]
                    }
                },
                {
                    dayNumber: 3,
                    activities: {
                        create: [
                            { time: "10:00", title: "Sidi Saiyyed Mosque", location: "Gheekanta", notes: "Famous for 'Jaali' windows", status: "upcoming", lat: 23.0267, lng: 72.5811 },
                            { time: "13:00", title: "Lunch at Manek Chowk", location: "Old City", notes: "Try the Gwalior Dosa", status: "upcoming", lat: 23.0243, lng: 72.5898 },
                            { time: "17:00", title: "Departure", location: "AMD Airport", notes: "Flight AI-456 to BOM", status: "upcoming", lat: 23.0734, lng: 72.6266 }
                        ]
                    }
                }
            ]
        }
    },
    {
        client: "Amit Patel",
        destination: "Goa, India",
        status: "Active",
        dateRange: "Dec 24 - Dec 27",
        age: 29,
        days: 4,
        email: "amit.patel@example.com",
        mobile: "+91 98765 12345",
        origin: "Mumbai",
        from: "Mumbai",
        to: "Goa",
        totalDays: 4,
        flights: {
            create: [
                { type: "Departure", date: "2023-12-24", airport: "BOM", airline: "SpiceJet", flightNumber: "SG-889", flightTime: "09:00", arrivalTime: "10:15", lat: 19.0886, lng: 72.8687 },
                { type: "Return", date: "2023-12-27", airport: "GOI", airline: "IndiGo", flightNumber: "6E-554", flightTime: "16:00", arrivalTime: "17:15", lat: 15.3800, lng: 73.8314 }
            ]
        },
        hotelStays: {
            create: [
                { hotelName: "Taj Fort Aguada", checkIn: "2023-12-24", checkOut: "2023-12-27", notes: "Sea view suite", lat: 15.4920, lng: 73.7737 }
            ]
        },
        itineraryDays: {
            create: [
                {
                    dayNumber: 1,
                    activities: {
                        create: [
                            { time: "11:00", title: "Arrival at GOI Airport", location: "Dabolim Airport", notes: "Cab picked up", status: "completed", lat: 15.3800, lng: 73.8314 },
                            { time: "14:00", title: "Check-in: Taj Fort Aguada", location: "Sinquerim, Candolim", notes: "Sea view suite", status: "completed", lat: 15.4920, lng: 73.7737 },
                            { time: "17:00", title: "Sunset at Chapora Fort", location: "Chapora", notes: "Dil Chahta Hai point", status: "upcoming", lat: 15.6061, lng: 73.7369 }
                        ]
                    }
                },
                {
                    dayNumber: 2,
                    activities: {
                        create: [
                            { time: "10:00", title: "Water Sports", location: "Calangute Beach", notes: "Parasailing & Jet Ski", status: "upcoming", lat: 15.5494, lng: 73.7535 },
                            { time: "13:00", title: "Lunch at Britto's", location: "Baga Beach", notes: "Try the seafood platter", status: "upcoming", lat: 15.5553, lng: 73.7517 },
                            { time: "20:00", title: "Casino Royale", location: "Panjim", notes: "Dress code: Formal", status: "upcoming", lat: 15.4839, lng: 73.8278 }
                        ]
                    }
                },
                {
                    dayNumber: 3,
                    activities: {
                        create: [
                            { time: "09:00", title: "South Goa Tour", location: "Old Goa", notes: "Basilica of Bom Jesus", status: "upcoming", lat: 15.5009, lng: 73.9116 },
                            { time: "12:00", title: "Mangueshi Temple", location: "Ponda", notes: "Ancient Shiva temple", status: "upcoming", lat: 15.4057, lng: 73.9687 },
                            { time: "16:00", title: "Colva Beach", location: "Salcete", notes: "Relaxing evening", status: "upcoming", lat: 15.2764, lng: 73.9186 }
                        ]
                    }
                },
                {
                    dayNumber: 4,
                    activities: {
                        create: [
                            { time: "10:00", title: "Fontainhas Walk", location: "Panjim", notes: "Latin Quarter photography", status: "upcoming", lat: 15.4862, lng: 73.8323 },
                            { time: "13:00", title: "Shopping at Mapusa Market", location: "Mapusa", notes: "Buy cashews + souvenirs", status: "upcoming", lat: 15.5947, lng: 73.8123 },
                            { time: "16:00", title: "Departure", location: "Dabolim Airport", notes: "Flight back to Mumbai", status: "upcoming", lat: 15.3800, lng: 73.8314 }
                        ]
                    }
                }
            ]
        }
    },
    {
        client: "Priya Sharma",
        destination: "Shimla, Himachal Pradesh",
        status: "Draft",
        dateRange: "Jan 10 - Jan 15",
        age: 34,
        days: 5,
        email: "priya.sharma@example.com",
        mobile: "+91 99887 76655",
        origin: "Delhi",
        from: "Delhi",
        to: "Shimla",
        totalDays: 5,
        flights: {
            create: [] // Road Trip
        },
        hotelStays: {
            create: [
                { hotelName: "Wildflower Hall", checkIn: "2024-01-10", checkOut: "2024-01-13", notes: "Luxury stay in Himalayas", lat: 31.1048, lng: 77.1734 }
            ]
        },
        itineraryDays: {
            create: [
                {
                    dayNumber: 1,
                    activities: {
                        create: [
                            { time: "08:00", title: "Drive to Shimla", location: "Delhi to Shimla", notes: "Stop at Murthal for Parathas", status: "completed", lat: 28.7041, lng: 77.1025 },
                            { time: "16:00", title: "Arrival & Check-in", location: "Wildflower Hall, Shimla", notes: "Luxury stay in Himalayas", status: "completed", lat: 31.1048, lng: 77.1734 },
                            { time: "18:00", title: "Mall Road Stroll", location: "The Ridge, Shimla", notes: "Visit Christ Church", status: "current", lat: 31.1041, lng: 77.1751 }
                        ]
                    }
                },
                {
                    dayNumber: 2,
                    activities: {
                        create: [
                            { time: "09:00", title: "Kufri Adventure Park", location: "Kufri", notes: "Yak ride and skiing", status: "upcoming", lat: 31.0979, lng: 77.2678 },
                            { time: "14:00", title: "Jakhu Temple", location: "Jakhu Hill", notes: "Beware of monkeys!", status: "upcoming", lat: 31.1013, lng: 77.1855 }
                        ]
                    }
                },
                {
                    dayNumber: 3,
                    activities: {
                        create: [
                            { time: "08:00", title: "Travel to Manali", location: "Shimla to Manali", notes: "Scenic drive via Mandi", status: "upcoming", lat: 32.2432, lng: 77.1892 },
                            { time: "13:00", title: "River Rafting", location: "Kullu", notes: "White water rafting", status: "upcoming", lat: 31.9566, lng: 77.1095 }
                        ]
                    }
                },
                {
                    dayNumber: 4,
                    activities: {
                        create: [
                            { time: "10:00", title: "Solang Valley", location: "Solang Valley", notes: "Paragliding", status: "upcoming", lat: 32.3126, lng: 77.1623 },
                            { time: "15:00", title: "Hadimba Temple", location: "Old Manali", notes: "Ancient wooden temple", status: "upcoming", lat: 32.2482, lng: 77.1806 }
                        ]
                    }
                },
                {
                    dayNumber: 5,
                    activities: {
                        create: [
                            { time: "09:00", title: "Jogini Waterfalls Trek", location: "Vashisht Village", notes: "Morning trek", status: "upcoming", lat: 32.2644, lng: 77.1956 },
                            { time: "14:00", title: "Manali Mall Road", location: "Manali", notes: "Souvenir shopping", status: "upcoming", lat: 32.2396, lng: 77.1887 },
                            { time: "18:00", title: "Bus to Delhi", location: "Manali Bus Stand", notes: "Overnight Volvo", status: "upcoming", lat: 32.2359, lng: 77.1925 }
                        ]
                    }
                }
            ]
        }
    },
    {
        client: "Anjali Mehta",
        destination: "Kerala, India",
        status: "Active",
        dateRange: "Feb 14 - Feb 20",
        age: 31,
        days: 7,
        email: "anjali.m@example.com",
        mobile: "+91 98989 89898",
        origin: "Bangalore",
        from: "Bangalore",
        to: "Kerala",
        totalDays: 7,
        flights: {
            create: [
                { type: "Departure", date: "2024-02-14", airport: "BLR", airline: "IndiGo", flightNumber: "6E-332", flightTime: "07:00", arrivalTime: "08:15", lat: 13.1986, lng: 77.7066 },
                { type: "Return", date: "2024-02-20", airport: "TRV", airline: "IndiGo", flightNumber: "6E-445", flightTime: "15:00", arrivalTime: "16:15", lat: 8.4821, lng: 76.9205 }
            ]
        },
        hotelStays: {
            create: [
                { hotelName: "Munnar Tea Estates", checkIn: "2024-02-14", checkOut: "2024-02-16", notes: "Scenic view", lat: 10.0889, lng: 77.0595 },
                { hotelName: "Alleppey Houseboat", checkIn: "2024-02-17", checkOut: "2024-02-18", notes: "Full board", lat: 9.4900, lng: 76.3500 },
                { hotelName: "Kovalam Beach Resort", checkIn: "2024-02-18", checkOut: "2024-02-20", notes: "Beach access", lat: 8.4020, lng: 76.9787 }
            ]
        },
        itineraryDays: {
            create: [
                {
                    dayNumber: 1,
                    activities: {
                        create: [
                            { time: "09:00", title: "Arrival at Cochin", location: "COK Airport", notes: "Driver waiting", status: "completed", lat: 10.1518, lng: 76.3930 },
                            { time: "13:00", title: "Drive to Munnar", location: "Munnar", notes: "Stop at Cheeyappara Waterfalls", status: "current", lat: 10.0889, lng: 77.0595 }
                        ]
                    }
                },
                {
                    dayNumber: 2,
                    activities: {
                        create: [
                            { time: "09:00", title: "Eravikulam National Park", location: "Munnar", notes: "See Nilgiri Tahr", status: "upcoming", lat: 10.1345, lng: 77.0867 },
                            { time: "14:00", title: "Tea Museum", location: "Nallathanni Estate", notes: "Tea tasting session", status: "upcoming", lat: 10.0912, lng: 77.0601 }
                        ]
                    }
                },
                {
                    dayNumber: 3,
                    activities: {
                        create: [
                            { time: "08:00", title: "Drive to Thekkady", location: "Thekkady", notes: "Scenic drive through hills", status: "upcoming", lat: 9.6056, lng: 77.1656 },
                            { time: "14:00", title: "Periyar Lake Boating", location: "Periyar Wildlife Sanctuary", notes: "Spot elephants", status: "upcoming", lat: 9.5833, lng: 77.1833 },
                            { time: "18:00", title: "Kathakali Show", location: "Kumily", notes: "Traditional dance", status: "upcoming", lat: 9.6071, lng: 77.1673 }
                        ]
                    }
                },
                {
                    dayNumber: 4,
                    activities: {
                        create: [
                            { time: "09:00", title: "Drive to Alleppey", location: "Alleppey", notes: "Venice of the East", status: "upcoming", lat: 9.4981, lng: 76.3388 },
                            { time: "13:00", title: "Houseboat Check-in", location: "Alleppey Backwaters", notes: "Lunch on board", status: "upcoming", lat: 9.4900, lng: 76.3500 }
                        ]
                    }
                },
                {
                    dayNumber: 5,
                    activities: {
                        create: [
                            { time: "10:00", title: "Drive to Kovalam", location: "Kovalam", notes: "Beach destination", status: "upcoming", lat: 8.4020, lng: 76.9787 },
                            { time: "16:00", title: "Lighthouse Beach", location: "Kovalam Beach", notes: "Sunset view", status: "upcoming", lat: 8.3887, lng: 76.9772 }
                        ]
                    }
                },
                {
                    dayNumber: 6,
                    activities: {
                        create: [
                            { time: "09:00", title: "Padmanabhaswamy Temple", location: "Thiruvananthapuram", notes: "Traditional dress code mandatory", status: "upcoming", lat: 8.4831, lng: 76.9436 },
                            { time: "14:00", title: "Napier Museum", location: "Trivandrum", notes: "Art and history", status: "upcoming", lat: 8.5085, lng: 76.9554 }
                        ]
                    }
                },
                {
                    dayNumber: 7,
                    activities: {
                        create: [
                            { time: "10:00", title: "Relax at Resort", location: "Kovalam", notes: "Leisure morning", status: "upcoming", lat: 8.4000, lng: 76.9700 },
                            { time: "15:00", title: "Departure", location: "TRV Airport", notes: "Flight back to Bangalore", status: "upcoming", lat: 8.4821, lng: 76.9205 }
                        ]
                    }
                }
            ]
        }
    },
    {
        client: "Sarah Jenkins",
        destination: "Dubai, UAE",
        status: "Completed",
        dateRange: "Jan 05 - Jan 08",
        age: 45,
        days: 4,
        email: "sarah.j@example.com",
        mobile: "+971 50 123 4567",
        origin: "London",
        from: "London",
        to: "Dubai",
        totalDays: 4,
        flights: {
            create: [
                { type: "Departure", date: "2024-01-05", airport: "LHR", airline: "Emirates", flightNumber: "EK004", flightTime: "20:40", arrivalTime: "07:30", lat: 51.4700, lng: -0.4543 },
                { type: "Return", date: "2024-01-08", airport: "DXB", airline: "Emirates", flightNumber: "EK003", flightTime: "16:00", arrivalTime: "20:00", lat: 25.2532, lng: 55.3657 }
            ]
        },
        hotelStays: {
            create: [
                { hotelName: "Atlantis The Palm", checkIn: "2024-01-05", checkOut: "2024-01-08", notes: "Ocean View - ATL-9988", lat: 25.1304, lng: 55.1171 }
            ]
        },
        itineraryDays: {
            create: [
                {
                    dayNumber: 1,
                    activities: {
                        create: [
                            { time: "09:00", title: "Arrival at DXB", location: "Dubai International Airport", notes: "VIP Transfer included", status: "completed", lat: 25.2532, lng: 55.3657 },
                            { time: "14:00", title: "Check-in: Atlantis", location: "The Palm Jumeirah", notes: "Early check-in requested", status: "completed", lat: 25.1304, lng: 55.1171 },
                            { time: "19:00", title: "Dinner at Nobu", location: "Atlantis", notes: "Reservation at 7:30 PM", status: "completed", lat: 25.1304, lng: 55.1171 }
                        ]
                    }
                },
                {
                    dayNumber: 2,
                    activities: {
                        create: [
                            { time: "10:00", title: "Burj Khalifa", location: "Downtown Dubai", notes: "At the Top tickets (Level 124)", status: "completed", lat: 25.1972, lng: 55.2744 },
                            { time: "13:00", title: "Dubai Mall", location: "Downtown Dubai", notes: "Shopping & Aquarium", status: "completed", lat: 25.1985, lng: 55.2796 },
                            { time: "16:00", title: "Fountain Show", location: "Burj Lake", notes: "Watch from Apple Store balcony", status: "completed", lat: 25.1975, lng: 55.2748 }
                        ]
                    }
                },
                {
                    dayNumber: 3,
                    activities: {
                        create: [
                            { time: "15:00", title: "Desert Safari", location: "Dubai Desert Conservation Reserve", notes: "Dune bashing & BBQ dinner", status: "completed", lat: 24.8324, lng: 55.6708 }
                        ]
                    }
                },
                {
                    dayNumber: 4,
                    activities: {
                        create: [
                            { time: "10:00", title: "Old Dubai Tour", location: "Al Fahidi Historical Neighbourhood", notes: "Visit Coffee Museum", status: "completed", lat: 25.2638, lng: 55.3006 },
                            { time: "12:00", title: "Abra Ride", location: "Dubai Creek", notes: "Cross to Spice Souk", status: "completed", lat: 25.2662, lng: 55.2977 },
                            { time: "16:00", title: "Departure", location: "DXB Airport", notes: "Flight EK003 back to LHR", status: "completed", lat: 25.2532, lng: 55.3657 }
                        ]
                    }
                }
            ]
        }
    }
];

async function main() {
    console.log('Cleaning existing data...');
    await prisma.activity.deleteMany({});
    await prisma.day.deleteMany({});
    await prisma.itinerary.deleteMany({});

    console.log('Seeding data with computed activity order...');

    for (const itinerary of itineraries) {
        // Deep-clone to avoid mutating the const above
        const data = JSON.parse(JSON.stringify(itinerary));

        // Compute server-side chronological order for each day's activities
        if (data.itineraryDays?.create) {
            for (const day of data.itineraryDays.create) {
                if (day.activities?.create?.length) {
                    day.activities.create = computeActivityOrder(day.activities.create);
                }
            }
        }

        const result = await prisma.itinerary.create({ data });
        console.log(`Created itinerary id=${result.id} (${data.client})`);
    }
    console.log('Seeding finished.');
}

main()
    .catch((e) => {
        console.error(e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
