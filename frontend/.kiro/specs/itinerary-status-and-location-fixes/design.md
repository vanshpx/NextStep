# Itinerary Status and Location Fixes - Bugfix Design

## Overview

This design addresses five interconnected bugs in the travel itinerary application that affect location accuracy, status management, and user feedback. The bugs span from incorrect GPS coordinates in seed data to missing auto-update logic for itinerary and activity statuses, absent visual feedback for issue reporting, and missing dashboard notifications. The fix strategy involves correcting seed data, implementing time-based status transitions, adding visual feedback mechanisms, and enhancing the dashboard notification system.

## Glossary

- **Bug_Condition (C)**: The conditions that trigger each of the five bugs
- **Property (P)**: The desired behavior when bug conditions are met
- **Preservation**: Existing functionality that must remain unchanged
- **Status Transition**: Automatic change of itinerary/activity status based on time
- **useGlobalTime**: Hook that provides current timestamp for time-based calculations
- **useActivityStatus**: Hook that calculates activity status based on start/end times
- **ItineraryContext**: React context managing itinerary state and API interactions
- **OpsPanel**: Dashboard component displaying "Needs Attention" and "Active Trips"

## Bug Details

### Bug 1: Incorrect Location Coordinates

#### Fault Condition

The seed data contains inaccurate GPS coordinates for activities at different physical locations, causing map markers to overlap.

**Formal Specification:**
```
FUNCTION isBugCondition1(activity)
  INPUT: activity with lat, lng, and location name
  OUTPUT: boolean
  
  RETURN activity.lat AND activity.lng exist
         AND coordinates do NOT match actual geographic position of activity.location
         AND multiple activities have identical/near-identical coordinates despite different locations
END FUNCTION
```

#### Examples

- Anju Beach Resort & Spa (lat: 15.5535, lng: 73.7634) and Sunset Cruise on Mandovi River (lat: 15.5012, lng: 73.8274) show nearly identical coordinates despite being different locations
- Multiple activities render overlapping map markers that cannot be individually selected
- Users cannot distinguish between different locations on the map

### Bug 2: Itinerary Status Not Auto-Updating

#### Fault Condition

The itinerary status does not automatically transition from "Upcoming" to "Active" when the trip start date is reached, and does not transition from "Active" to "Completed" when the trip end date passes.

**Formal Specification:**
```
FUNCTION isBugCondition2(itinerary, currentTime)
  INPUT: itinerary with status, flights array, itineraryDays
  OUTPUT: boolean
  
  LET startDate = itinerary.flights.find(f => f.type === 'Departure').date
  LET endDate = itinerary.flights.find(f => f.type === 'Return').date
  
  RETURN (itinerary.status === 'Upcoming' AND currentTime >= startDate)
         OR (itinerary.status === 'Active' AND currentTime >= endDate)
END FUNCTION
```

#### Examples

- Itinerary with departure date of Jan 15, 2025 remains "Upcoming" on Jan 16, 2025
- Itinerary with return date of Jan 20, 2025 remains "Active" on Jan 21, 2025
- Dashboard shows incorrect status for trips that should have transitioned

### Bug 3: Activity Status Not Auto-Updating

#### Fault Condition

Individual activity status does not automatically update from "upcoming" to "current" to "completed" based on the activity's time window.

**Formal Specification:**
```
FUNCTION isBugCondition3(activity, currentTime)
  INPUT: activity with startTime, endTime, status
  OUTPUT: boolean
  
  RETURN (activity.status === 'upcoming' AND currentTime >= activity.startTime)
         OR (activity.status === 'current' AND currentTime >= activity.endTime)
         OR (activity status in database does NOT reflect time-based state)
END FUNCTION
```

#### Examples

- Activity scheduled for 10:00 AM still shows "upcoming" at 10:30 AM
- Activity ending at 12:00 PM still shows "current" at 1:00 PM
- Database persists outdated status values instead of computing from time

### Bug 4: Report Issue Visual Feedback Missing

#### Fault Condition

When a user reports an issue via the DisruptionModal, there is no visual confirmation that the report was submitted successfully beyond a browser alert.

**Formal Specification:**
```
FUNCTION isBugCondition4(userAction, uiState)
  INPUT: userAction (report issue submission), uiState (UI feedback elements)
  OUTPUT: boolean
  
  RETURN userAction === 'submit_disruption'
         AND uiState.visualFeedback === null
         AND uiState.toastNotification === null
         AND uiState.modalConfirmation === null
END FUNCTION
```

#### Examples

- User clicks "Submit Report" and modal closes with only a browser alert
- No toast notification appears confirming the issue was reported
- No visual indicator shows the activity is now marked as disrupted
- User is unsure if the report was successfully submitted

### Bug 5: Dashboard Notifications Missing

#### Fault Condition

The dashboard "Needs Attention" panel does not show notifications for newly reported issues or status changes that require agent action.

**Formal Specification:**
```
FUNCTION isBugCondition5(itinerary, dashboardState)
  INPUT: itinerary with status='Disrupted', dashboardState
  OUTPUT: boolean
  
  RETURN itinerary.status === 'Disrupted'
         AND itinerary.issueSummary exists
         AND dashboardState.needsAttentionPanel does NOT highlight this itinerary prominently
         AND dashboardState.notificationCount does NOT increment
END FUNCTION
```

#### Examples

- User reports issue on client view page, but dashboard doesn't show notification badge
- "Needs Attention" panel shows disrupted itinerary but without timestamp or urgency indicator
- Agent doesn't receive real-time notification of newly reported issues

## Expected Behavior

### Bug 1: Correct Location Coordinates

**Expected Behavior:**
- Each activity SHALL have accurate GPS coordinates matching its actual geographic location
- Map markers SHALL render at distinct positions without overlap
- Users SHALL be able to select and interact with individual markers

### Bug 2: Itinerary Status Auto-Updates

**Expected Behavior:**
- Itinerary status SHALL automatically transition from "Upcoming" to "Active" when departure date is reached
- Itinerary status SHALL automatically transition from "Active" to "Completed" when return date passes
- Status transitions SHALL occur without manual intervention

### Bug 3: Activity Status Auto-Updates

**Expected Behavior:**
- Activity status SHALL be computed dynamically based on current time vs. startTime/endTime
- Activities SHALL show "upcoming" before startTime, "current" during time window, "completed" after endTime
- Database SHALL store base status, but UI SHALL display computed time-based status

### Bug 4: Report Issue Visual Feedback

**Expected Behavior:**
- User SHALL see toast notification confirming issue report submission
- Activity card SHALL visually update to show "Disrupted" status
- Modal SHALL show success state before closing

### Bug 5: Dashboard Notifications

**Expected Behavior:**
- Dashboard SHALL show notification badge for new disruptions
- "Needs Attention" panel SHALL highlight disrupted itineraries with red dot
- Panel SHALL show timestamp of when issue was reported

### Preservation Requirements

**Unchanged Behaviors:**
- Existing map rendering logic for valid coordinates SHALL continue to work
- Manual status updates via builder form SHALL continue to function
- DisruptionModal submission flow SHALL preserve existing API call structure
- Dashboard filtering and search functionality SHALL remain unchanged
- All existing itinerary CRUD operations SHALL work as before

**Scope:**
All inputs that do NOT involve the specific bug conditions should be completely unaffected by these fixes. This includes:
- Itineraries with correct coordinates in seed data
- Manual status changes via the builder interface
- Activities with manually set status values
- Dashboard display of non-disrupted itineraries
- All other itinerary management features

## Hypothesized Root Cause

Based on the bug descriptions and code analysis, the most likely issues are:

### Bug 1: Incorrect Location Coordinates
1. **Seed Data Inaccuracy**: The `prisma/seed.ts` file contains hardcoded GPS coordinates that were not verified against actual locations
2. **No Geocoding Validation**: The seed script does not validate coordinates against location names
3. **Copy-Paste Errors**: Similar coordinates were likely copied between different activities

### Bug 2: Itinerary Status Not Auto-Updating
1. **Partial Implementation**: The `ItineraryContext.tsx` has logic to transition "Upcoming" → "Active" but is missing "Active" → "Completed" logic
2. **Client-Side Only**: Status transitions happen only in `fetchItineraries()` on page load, not continuously
3. **No Background Job**: There's no server-side cron job or scheduled task to update statuses

### Bug 3: Activity Status Not Auto-Updating
1. **Database Persistence**: Activity status is stored in the database as a static field instead of being computed
2. **Hook Not Used Everywhere**: The `useActivityStatus` hook exists but its computed status is not used to update the database
3. **Inconsistent State**: UI shows computed status but database retains old status value

### Bug 4: Report Issue Visual Feedback Missing
1. **Browser Alert Only**: The `handleDisruptionSubmit` function in `page.tsx` uses `alert()` instead of a toast notification system
2. **No Toast Library**: The project doesn't have a toast notification library integrated
3. **Immediate Modal Close**: The modal closes immediately after submission without showing success state

### Bug 5: Dashboard Notifications Missing
1. **No Real-Time Updates**: The dashboard doesn't poll or use WebSockets for real-time updates
2. **No Notification Badge**: The OpsPanel component doesn't show a count of new issues
3. **No Timestamp Display**: The "Needs Attention" panel doesn't show when issues were reported
4. **Missing Urgency Indicators**: No visual distinction between old and new disruptions

## Correctness Properties

Property 1: Fault Condition - Location Coordinates Accuracy

_For any_ activity in the seed data where the location name is specified, the fixed seed script SHALL assign GPS coordinates that accurately correspond to the actual geographic position of that location, ensuring map markers render at distinct, correct positions.

**Validates: Requirements 2.1 (Bug 1 Expected Behavior)**

Property 2: Fault Condition - Itinerary Status Transitions

_For any_ itinerary where the current time has passed the departure date and status is "Upcoming", OR where the current time has passed the return date and status is "Active", the fixed system SHALL automatically transition the itinerary status to the correct state ("Active" or "Completed" respectively).

**Validates: Requirements 2.2 (Bug 2 Expected Behavior)**

Property 3: Fault Condition - Activity Status Computation

_For any_ activity with defined startTime and endTime, the fixed system SHALL compute and display the activity status dynamically based on the current time, showing "upcoming" before startTime, "current" during the time window, and "completed" after endTime.

**Validates: Requirements 2.3 (Bug 3 Expected Behavior)**

Property 4: Fault Condition - Issue Report Visual Feedback

_For any_ user action that submits a disruption report, the fixed system SHALL display a toast notification confirming successful submission, update the activity card to show "Disrupted" status, and provide visual feedback before closing the modal.

**Validates: Requirements 2.4 (Bug 4 Expected Behavior)**

Property 5: Fault Condition - Dashboard Notifications

_For any_ itinerary that transitions to "Disrupted" status, the fixed dashboard SHALL display a notification badge, highlight the itinerary in the "Needs Attention" panel with a red dot, and show the timestamp of when the issue was reported.

**Validates: Requirements 2.5 (Bug 5 Expected Behavior)**

Property 6: Preservation - Existing Functionality

_For any_ itinerary operation that does NOT involve the specific bug conditions (incorrect coordinates, status transitions, issue reporting, or dashboard notifications), the fixed system SHALL produce exactly the same behavior as the original system, preserving all existing CRUD operations, map rendering, and UI interactions.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5 (Preservation Requirements)**

## Fix Implementation

### Bug 1: Correct Location Coordinates

**File**: `prisma/seed.ts`

**Specific Changes**:
1. **Research Accurate Coordinates**: Use Google Maps or geocoding APIs to find correct lat/lng for each location
2. **Update Activity Coordinates**: Replace hardcoded coordinates with accurate values
3. **Update Flight Coordinates**: Verify airport coordinates are correct
4. **Update Hotel Coordinates**: Verify hotel coordinates match actual locations
5. **Add Validation Comments**: Document the source of coordinates for future reference

**Example Fix**:
```typescript
// Before (incorrect)
{ title: "Anju Beach Resort & Spa", lat: 15.5535, lng: 73.7634 }
{ title: "Sunset Cruise on Mandovi River", lat: 15.5012, lng: 73.8274 }

// After (correct - example coordinates)
{ title: "Anju Beach Resort & Spa", lat: 15.2993, lng: 74.1240 } // Actual resort location
{ title: "Sunset Cruise on Mandovi River", lat: 15.4909, lng: 73.8278 } // Mandovi River dock
```

### Bug 2: Itinerary Status Auto-Updates

**File**: `src/context/ItineraryContext.tsx`

**Function**: `fetchItineraries`

**Specific Changes**:
1. **Add Completed Transition Logic**: After the existing "Upcoming" → "Active" logic, add logic to check if "Active" itineraries should transition to "Completed"
2. **Check Return Flight Date**: Find the return flight and compare its date to current date
3. **Update Status to Completed**: If return date has passed, update status to "Completed"
4. **Fire API Update**: Send PATCH request to update status on server

**Implementation**:
```typescript
// Add after existing Upcoming → Active logic (around line 130)
if (itinerary.status === 'Active' && itinerary.flights && itinerary.flights.length > 0) {
    let endDate: Date | null = null;
    
    // Find return flight
    const returnFlight = itinerary.flights.find(f => f.type === 'Return');
    if (returnFlight && returnFlight.date) {
        endDate = new Date(returnFlight.date);
    }
    
    if (endDate && endDate < today) {
        console.log(`Auto-completing itinerary ${itinerary.id}`);
        itinerary.status = 'Completed';
        
        // Fire and forget update to server
        fetch(`/api/itineraries/${itinerary.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'Completed' })
        });
    }
}
```

### Bug 3: Activity Status Auto-Updates

**Note**: This bug is partially addressed by the existing `useActivityStatus` hook. The issue is that the database stores static status values. The fix is to ensure the UI always uses the computed status from the hook, not the database value.

**File**: `src/app/view/[id]/page.tsx`

**Component**: `TimelineActivityCard`

**Specific Changes**:
1. **Use Computed Status**: The component already calls `useActivityStatus` but doesn't use it consistently
2. **Remove Database Status Dependency**: Don't rely on `activity.status` from database for display logic
3. **Update Disruption Check**: Keep disruption check based on database status, but use computed status for time-based display

**Implementation**:
```typescript
// Current code (line 138-140)
const isDisrupted = activity.status === 'issue';
const { status, progressPercentage } = useActivityStatus(activity.startTime, activity.endTime, isDisrupted);

// This is already correct - the computed status is used for display
// The fix is to ensure we don't update the database with time-based statuses
// Only manual status changes (like 'issue') should be persisted
```

**Additional Change**: Ensure the builder form and API don't automatically set status based on time when creating/updating activities.

### Bug 4: Report Issue Visual Feedback

**Files**: 
- `src/app/view/[id]/page.tsx` (add toast notification)
- `src/components/client/DisruptionModal.tsx` (add success state)
- Install toast library: `npm install sonner`

**Specific Changes**:

1. **Install Toast Library**: Add `sonner` for toast notifications
2. **Import Toast Components**: Add Toaster component to layout
3. **Replace Alert with Toast**: Update `handleDisruptionSubmit` to use toast
4. **Add Success State to Modal**: Show checkmark before closing
5. **Update Activity Card Immediately**: Optimistically update UI

**Implementation in `page.tsx`**:
```typescript
// Add import
import { toast } from 'sonner';

// Update handleDisruptionSubmit (around line 242)
const handleDisruptionSubmit = async (type: string, details?: string) => {
    console.log("Disruption reported:", type, details, "for activity:", disruptionActivity?.title);

    try {
        await updateItinerary(itinerary.id, {
            status: 'Disrupted',
            issueSummary: type
        });
        
        // Replace alert with toast
        toast.success('Issue Reported', {
            description: `"${type}" has been reported. Support team notified.`,
            duration: 4000,
        });
    } catch (error) {
        console.error("Failed to report disruption", error);
        toast.error('Failed to Report Issue', {
            description: 'Please try again or contact support.',
            duration: 4000,
        });
    }

    setDisruptionActivity(null);
};
```

**Implementation in `layout.tsx`**:
```typescript
// Add to root layout
import { Toaster } from 'sonner';

export default function RootLayout({ children }) {
    return (
        <html>
            <body>
                {children}
                <Toaster position="top-right" />
            </body>
        </html>
    );
}
```

### Bug 5: Dashboard Notifications

**File**: `src/components/dashboard/OpsPanel.tsx`

**Component**: `NeedsAttentionCard`

**Specific Changes**:
1. **Add Timestamp Display**: Show when issue was reported using `updatedAt` field
2. **Add Notification Badge**: Show count of new disruptions (reported in last 24 hours)
3. **Add Urgency Indicator**: Highlight recently reported issues differently
4. **Sort by Recency**: Show most recent disruptions first

**Implementation**:
```typescript
// Update buildAttentionList function (around line 90)
function buildAttentionList(itineraries: Itinerary[]): AttentionItem[] {
    const items: AttentionItem[] = [];
    const now = Date.now();
    const twentyFourHoursAgo = now - (24 * 60 * 60 * 1000);
    
    for (const it of itineraries) {
        if (it.status === "Disrupted") {
            const isRecent = it.updatedAt && new Date(it.updatedAt).getTime() > twentyFourHoursAgo;
            const timestamp = it.updatedAt ? new Date(it.updatedAt).toLocaleString() : 'Unknown';
            
            items.push({ 
                itinerary: it, 
                issue: it.issueSummary || "Issue reported", 
                dot: "red",
                timestamp,
                isRecent 
            });
            continue;
        }
        // ... rest of existing logic
    }
    
    // Sort: recent disruptions first, then by dot color
    return items.sort((a, b) => {
        if (a.isRecent && !b.isRecent) return -1;
        if (!a.isRecent && b.isRecent) return 1;
        return (a.dot === "red" ? -1 : b.dot === "red" ? 1 : 0);
    });
}

// Update interface (around line 88)
interface AttentionItem { 
    itinerary: Itinerary; 
    issue: string; 
    dot: "red" | "amber";
    timestamp?: string;
    isRecent?: boolean;
}

// Update NeedsAttentionCard render (around line 150)
<div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
    <span style={{ 
        width: 8, 
        height: 8, 
        borderRadius: "50%", 
        flexShrink: 0, 
        background: dot === "red" ? "#ef4444" : "#f59e0b",
        ...(isRecent && { animation: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite" })
    }} />
    <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
        {itinerary.c} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>• {itinerary.d}</span>
    </p>
    {isRecent && (
        <span style={{ 
            fontSize: "10px", 
            background: "#fee2e2", 
            color: "#991b1b", 
            padding: "2px 6px", 
            borderRadius: "4px",
            fontWeight: 600,
            textTransform: "uppercase"
        }}>NEW</span>
    )}
</div>
<p style={{ fontSize: "13px", color: "#000000", margin: 0, paddingLeft: 16 }}>
    <span style={{ fontWeight: 600 }}>Issue:</span> {issue}
    {timestamp && <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>• {timestamp}</span>}
</p>
```

**Database Schema Update**:
The `updatedAt` field already exists in the Prisma schema and is automatically updated. No schema changes needed.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate each bug on unfixed code, then verify the fixes work correctly and preserve existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate all 5 bugs BEFORE implementing fixes. Confirm or refute the root cause analysis.

**Test Plan**: Write tests that simulate each bug condition and assert the expected failures. Run these tests on the UNFIXED code to observe failures and understand root causes.

**Test Cases**:

1. **Bug 1 - Location Coordinates Test**: Query seed data and verify coordinates match actual locations (will fail on unfixed code)
   - Load seed data and extract all activities with coordinates
   - For each activity, verify lat/lng is within expected range for location
   - Assert that activities at different locations have sufficiently different coordinates (>0.01 degree difference)

2. **Bug 2 - Itinerary Status Transition Test**: Simulate time passing and verify status updates (will fail on unfixed code)
   - Create itinerary with departure date in the past, status "Upcoming"
   - Call fetchItineraries and verify status transitions to "Active"
   - Create itinerary with return date in the past, status "Active"
   - Call fetchItineraries and verify status transitions to "Completed" (will fail)

3. **Bug 3 - Activity Status Computation Test**: Verify activity status reflects current time (will fail on unfixed code)
   - Create activity with startTime in past, endTime in future, database status "upcoming"
   - Render TimelineActivityCard and verify displayed status is "current" (should pass - hook works)
   - Verify database status is NOT updated to "current" (should pass - this is correct behavior)

4. **Bug 4 - Visual Feedback Test**: Verify toast notification appears after issue report (will fail on unfixed code)
   - Render DisruptionModal and submit issue report
   - Assert toast notification appears with success message (will fail - uses alert)
   - Assert modal shows success state before closing (will fail - closes immediately)

5. **Bug 5 - Dashboard Notification Test**: Verify disrupted itineraries show in dashboard (will fail on unfixed code)
   - Create itinerary with status "Disrupted" and recent updatedAt timestamp
   - Render OpsPanel and verify "Needs Attention" shows the itinerary (should pass)
   - Verify "NEW" badge appears for recent disruptions (will fail - not implemented)
   - Verify timestamp is displayed (will fail - not implemented)

**Expected Counterexamples**:
- Seed data contains duplicate/incorrect coordinates for distinct locations
- "Active" → "Completed" transition does not occur automatically
- Toast notifications do not appear (browser alert used instead)
- Dashboard does not show "NEW" badge or timestamps for disruptions

### Fix Checking

**Goal**: Verify that for all inputs where bug conditions hold, the fixed system produces the expected behavior.

**Pseudocode**:
```
FOR ALL bug IN [bug1, bug2, bug3, bug4, bug5] DO
  FOR ALL input WHERE isBugCondition(bug, input) DO
    result := fixedSystem(input)
    ASSERT expectedBehavior(bug, result)
  END FOR
END FOR
```

**Test Cases**:

1. **Bug 1 Fix Verification**: Verify all seed data has accurate coordinates
   - Load fixed seed data
   - For each activity, verify coordinates are accurate (manual verification or geocoding API)
   - Verify no overlapping markers on map

2. **Bug 2 Fix Verification**: Verify both status transitions work
   - Test "Upcoming" → "Active" transition (already works)
   - Test "Active" → "Completed" transition (new fix)

3. **Bug 3 Fix Verification**: Verify activity status is computed correctly
   - Test activity status computation at different times
   - Verify database status is not overwritten by time-based computation

4. **Bug 4 Fix Verification**: Verify toast notifications appear
   - Submit issue report and verify toast appears
   - Verify toast contains correct message
   - Verify modal closes after showing success

5. **Bug 5 Fix Verification**: Verify dashboard shows notifications
   - Create disrupted itinerary and verify "NEW" badge appears
   - Verify timestamp is displayed
   - Verify sorting places recent disruptions first

### Preservation Checking

**Goal**: Verify that for all inputs where bug conditions do NOT hold, the fixed system produces the same result as the original system.

**Pseudocode**:
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because it generates many test cases automatically and catches edge cases.

**Test Plan**: Observe behavior on UNFIXED code first for non-bug scenarios, then write property-based tests capturing that behavior.

**Test Cases**:

1. **Map Rendering Preservation**: Verify map rendering works for activities with correct coordinates
   - Test that existing map component renders correctly
   - Test that marker clustering works
   - Test that marker selection works

2. **Manual Status Update Preservation**: Verify manual status changes via builder still work
   - Update itinerary status manually via builder form
   - Verify status is saved correctly
   - Verify no automatic transitions override manual changes

3. **CRUD Operations Preservation**: Verify all itinerary CRUD operations work
   - Create, read, update, delete itineraries
   - Verify all fields are preserved
   - Verify relationships (flights, hotels, days, activities) are maintained

4. **Dashboard Filtering Preservation**: Verify search and filtering continue to work
   - Test search by client name, destination, date
   - Verify filtering by status
   - Verify sorting

5. **Existing UI Interactions Preservation**: Verify all UI interactions work
   - Test button clicks, modal interactions
   - Test navigation between pages
   - Test responsive layout

### Unit Tests

- Test coordinate validation function (if added)
- Test status transition logic in isolation
- Test activity status computation hook
- Test toast notification triggering
- Test dashboard notification badge logic
- Test timestamp formatting

### Property-Based Tests

- Generate random itineraries with various dates and verify status transitions
- Generate random activities with various time windows and verify status computation
- Generate random coordinates and verify map rendering
- Test that all non-buggy inputs preserve existing behavior

### Integration Tests

- Test full flow: create itinerary → wait for status transition → verify dashboard updates
- Test full flow: report issue → verify toast → verify dashboard notification
- Test full flow: seed data → render map → verify markers are distinct
- Test that status transitions don't interfere with manual updates
- Test that multiple simultaneous status transitions work correctly

### Database Migration Tests

- Verify existing data is not corrupted by fixes
- Verify `updatedAt` timestamps are preserved
- Verify all relationships remain intact
- Test rollback scenarios
