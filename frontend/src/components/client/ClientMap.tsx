"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import { GoogleMap, Marker, OverlayView } from "@react-google-maps/api";
import { useGoogleMaps } from "@/lib/googleMaps";

interface Activity {
    id: number;
    title: string;
    time: string;
    location: string;
    status?: string;
    lat?: number;
    lng?: number;
}

interface ClientMapProps {
    activities: Activity[];
    flights?: unknown[];
    selectedActivity: Activity | null;
}

const mapContainerStyle = { width: "100%", height: "100%" };

// ─── SVG Marker Factories ──────────────────────────────────────────────────

function buildIcon(type: "completed" | "current" | "upcoming") {
    let svg: string;
    let size: number;

    if (type === "completed") {
        svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
  <circle cx="14" cy="14" r="13" fill="#22c55e" stroke="white" stroke-width="2"/>
  <path d="M8 14l4 4 8-8" stroke="white" stroke-width="2.5" fill="none"
    stroke-linecap="round" stroke-linejoin="round"/>
</svg>`;
        size = 28;
    } else if (type === "current") {
        svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
  <circle cx="14" cy="14" r="13" fill="#3b82f6" stroke="white" stroke-width="2"/>
  <circle cx="14" cy="14" r="5" fill="white"/>
</svg>`;
        size = 28;
    } else {
        svg = `<svg xmlns="http://www.w3.org/2000/svg" width="25" height="25" viewBox="0 0 28 28">
  <defs>
    <filter id="s" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="rgba(0,0,0,0.15)"/>
    </filter>
  </defs>
  <circle cx="14" cy="14" r="12" fill="#F59E0B" stroke="#FFFFFF" stroke-width="3.2" filter="url(#s)"/>
</svg>`;
        size = 25;
    }

    return {
        url: `data:image/svg+xml,${encodeURIComponent(svg)}`,
        scaledSize: new window.google.maps.Size(size, size),
        anchor: new window.google.maps.Point(size / 2, size / 2),
    };
}

// ─── Pulse Ring ────────────────────────────────────────────────────────────

function PulseRing({ position }: { position: google.maps.LatLngLiteral }) {
    return (
        <OverlayView position={position} mapPaneName={OverlayView.OVERLAY_MOUSE_TARGET}>
            <div style={{
                position: "absolute",
                transform: "translate(-50%, -50%)",
                width: 44, height: 44,
                borderRadius: "50%",
                background: "rgba(59,130,246,0.2)",
                animation: "pulse-ring 1.6s ease-out infinite",
                pointerEvents: "none",
            }} />
        </OverlayView>
    );
}

// ─── Custom Activity Popup ─────────────────────────────────────────────────

interface PopupData {
    activity: Activity;
    position: google.maps.LatLngLiteral;
}

function ActivityPopup({ data, onClose }: { data: PopupData; onClose: () => void }) {
    return (
        <OverlayView position={data.position} mapPaneName={OverlayView.FLOAT_PANE}>
            <div style={{
                position: "absolute",
                transform: "translate(-50%, calc(-100% - 20px))",
                pointerEvents: "auto",
            }}>
                {/* Card */}
                <div style={{
                    background: "white",
                    borderRadius: 12,
                    boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
                    padding: "10px 13px",
                    minWidth: 180,
                    maxWidth: 240,
                    fontFamily: "inherit",
                    position: "relative",
                }}>
                    {/* Close button */}
                    <button
                        onClick={onClose}
                        style={{
                            position: "absolute", top: 6, right: 8,
                            background: "none", border: "none",
                            fontSize: 14, color: "#9ca3af",
                            cursor: "pointer", lineHeight: 1,
                            padding: 0,
                        }}
                        aria-label="Close"
                    >✕</button>

                    {/* Title */}
                    <p style={{
                        fontWeight: 700, fontSize: 13,
                        color: "#111827", margin: "0 0 6px",
                        paddingRight: 16, lineHeight: 1.3,
                    }}>
                        {data.activity.title}
                    </p>

                    {/* Location */}
                    {data.activity.location && (
                        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                                stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                                <circle cx="12" cy="10" r="3" />
                            </svg>
                            <span style={{
                                fontSize: 11, color: "#6b7280", whiteSpace: "nowrap",
                                overflow: "hidden", textOverflow: "ellipsis", maxWidth: 180
                            }}>
                                {data.activity.location}
                            </span>
                        </div>
                    )}

                    {/* Time */}
                    {data.activity.time && (
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                                stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <circle cx="12" cy="12" r="10" />
                                <polyline points="12 6 12 12 16 14" />
                            </svg>
                            <span style={{ fontSize: 11, color: "#6b7280" }}>
                                {data.activity.time}
                            </span>
                        </div>
                    )}
                </div>

                {/* Arrow pointing down */}
                <div style={{
                    width: 0, height: 0,
                    borderLeft: "7px solid transparent",
                    borderRight: "7px solid transparent",
                    borderTop: "8px solid white",
                    margin: "0 auto",
                    filter: "drop-shadow(0 2px 2px rgba(0,0,0,0.08))",
                }} />
            </div>
        </OverlayView>
    );
}

// ─── Main Component ────────────────────────────────────────────────────────

export default function ClientMap({ activities = [], selectedActivity }: ClientMapProps) {
    const { isLoaded, loadError } = useGoogleMaps();
    const [map, setMap] = useState<google.maps.Map | null>(null);
    const [popup, setPopup] = useState<PopupData | null>(null);

    const validActivities = useMemo(
        () => activities.filter((a) => a.lat != null && a.lng != null),
        [activities]
    );

    const currentActivityId = useMemo(() => {
        const completedIds = new Set(
            activities.filter((a) => a.status === "completed").map((a) => a.id)
        );
        if (completedIds.size === 0 || completedIds.size === activities.length) return null;
        return activities.find((a) => !completedIds.has(a.id))?.id ?? null;
    }, [activities]);

    const onLoad = useCallback((m: google.maps.Map) => setMap(m), []);

    // Fit bounds to activity markers only, cap zoom to prevent world repetition
    useEffect(() => {
        if (!map || !isLoaded || validActivities.length === 0) return;
        const bounds = new window.google.maps.LatLngBounds();
        validActivities.forEach((a) => bounds.extend({ lat: a.lat!, lng: a.lng! }));
        map.fitBounds(bounds, 32); // 32px padding inside card edges

        // After fitBounds resolves, cap zoom so map never over-zooms or shows world repeat
        const listener = window.google.maps.event.addListenerOnce(map, "idle", () => {
            const z = map.getZoom() ?? 10;
            if (z > 14) map.setZoom(14);
            if (z < 3) map.setZoom(3);
        });
        return () => window.google.maps.event.removeListener(listener);
    }, [map, isLoaded, validActivities]);

    // Pan to selected activity
    useEffect(() => {
        if (!map || !selectedActivity?.lat || !selectedActivity?.lng) return;
        const pos = { lat: selectedActivity.lat!, lng: selectedActivity.lng! };
        map.panTo(pos);
        map.setZoom(14);
        setPopup({ activity: selectedActivity, position: pos });
    }, [map, selectedActivity]);

    if (loadError) return <div>Error loading maps</div>;
    if (!isLoaded)
        return (
            <div className="h-full w-full bg-gray-100 flex items-center justify-center text-sm text-gray-400">
                Loading Map…
            </div>
        );

    return (
        <>
            <style>{`
                @keyframes pulse-ring {
                    0%   { transform: translate(-50%,-50%) scale(0.6); opacity: 1; }
                    100% { transform: translate(-50%,-50%) scale(1.8); opacity: 0; }
                }
            `}</style>

            <GoogleMap
                mapContainerStyle={mapContainerStyle}
                zoom={5}
                onLoad={onLoad}
                onClick={() => setPopup(null)}
                options={{
                    mapTypeControl: false,
                    streetViewControl: false,
                    fullscreenControl: true,
                    minZoom: 3,          // prevents zooming out to world-repeat level
                    maxZoom: 18,
                    restriction: {
                        latLngBounds: {
                            north: 85, south: -85,
                            west: -180, east: 180,
                        },
                        strictBounds: true, // no panning beyond world bounds
                    },
                }}
            >
                {/* Activity Markers */}
                {validActivities.map((activity) => {
                    const isCurrent = activity.id === currentActivityId;
                    const isCompleted = activity.status === "completed";
                    const iconType = isCompleted ? "completed" : isCurrent ? "current" : "upcoming";
                    const pos = { lat: activity.lat!, lng: activity.lng! };

                    return (
                        <React.Fragment key={`act-${activity.id}`}>
                            {isCurrent && <PulseRing position={pos} />}
                            <Marker
                                position={pos}
                                icon={buildIcon(iconType)}
                                zIndex={isCurrent ? 10 : isCompleted ? 5 : 1}
                                onClick={() => setPopup({ activity, position: pos })}
                            />
                        </React.Fragment>
                    );
                })}

                {/* Custom popup */}
                {popup && (
                    <ActivityPopup
                        data={popup}
                        onClose={() => setPopup(null)}
                    />
                )}
            </GoogleMap>
        </>
    );
}
