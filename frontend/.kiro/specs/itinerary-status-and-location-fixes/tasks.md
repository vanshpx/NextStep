# Implementation Plan

## Phase 1: Exploration Tests (BEFORE Fixes)

- [x] 1. Write bug condition exploration tests for all 5 bugs
  - **Property 1: Fault Condition** - Multi-Bug Exploration Suite
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failures confirm the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they will validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate all 5 bugs exist
  - Write property-based test for Bug 1: Verify seed data contains incorrect/duplicate coordinates for distinct locations
  - Write test for Bug 2: Verify "Active" → "Completed" status transition does NOT occur (will fail)
  - Write test for Bug 3: Verify activity status computation works but database is not updated (should pass - this is correct)
  - Write test for Bug 4: Verify toast notification does NOT appear after issue report (will fail - uses browser alert)
  - Write test for Bug 5: Verify dashboard does NOT show "NEW" badge or timestamps for disruptions (will fail)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL for bugs 1, 2, 4, 5 (confirms bugs exist); Bug 3 test may pass (hook works, database behavior is correct)
  - Document counterexamples found:
    - Bug 1: List activities with duplicate/incorrect coordinates
    - Bug 2: Show itinerary that should be "Completed" but remains "Active"
    - Bug 4: Confirm browser alert is used instead of toast
    - Bug 5: Confirm missing "NEW" badge and timestamps
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

## Phase 2: Preservation Tests (BEFORE Fixes)

- [x] 2. Write preservation property tests (BEFORE implementing fixes)
  - **Property 2: Preservation** - Existing Functionality Preservation
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy scenarios
  - Write property-based test: Map rendering works correctly for activities with valid coordinates
  - Write property-based test: Manual status updates via builder form work correctly
  - Write property-based test: All itinerary CRUD operations preserve data integrity
  - Write property-based test: Dashboard filtering and search work correctly
  - Write property-based test: Existing UI interactions (navigation, modals, buttons) work correctly
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

## Phase 3: Implementation

- [x] 3. Fix Bug 1: Correct location coordinates in seed data

  - [x] 3.1 Research accurate GPS coordinates for all locations
    - Use Google Maps or geocoding API to find correct lat/lng for each activity location
    - Document the source of coordinates for future reference
    - Verify coordinates are sufficiently distinct (>0.01 degree difference for different locations)
    - _Bug_Condition: isBugCondition1(activity) where coordinates do NOT match actual location_
    - _Expected_Behavior: Each activity has accurate GPS coordinates matching actual geographic location_
    - _Preservation: Existing map rendering logic for valid coordinates continues to work_
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 3.2 Update seed data with correct coordinates
    - Edit `prisma/seed.ts`
    - Replace hardcoded coordinates for all activities with accurate values
    - Update flight coordinates if needed
    - Update hotel coordinates if needed
    - Add comments documenting coordinate sources
    - _Bug_Condition: Multiple activities have identical/near-identical coordinates despite different locations_
    - _Expected_Behavior: Map markers render at distinct positions without overlap_
    - _Preservation: Seed script structure and other data remain unchanged_
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 3.3 Run seed script and verify map markers
    - Run `npx prisma db seed` to populate database with corrected data
    - Open application and navigate to itinerary view page
    - Verify map markers render at distinct positions
    - Verify no overlapping markers
    - Verify users can select individual markers
    - _Requirements: 2.1_

  - [x] 3.4 Verify Bug 1 exploration test now passes
    - **Property 1: Expected Behavior** - Accurate Location Coordinates
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run Bug 1 exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms coordinates are accurate)
    - _Requirements: 2.1_

- [x] 4. Fix Bug 2: Add itinerary status auto-update logic

  - [x] 4.1 Implement "Active" → "Completed" status transition
    - Edit `src/context/ItineraryContext.tsx`
    - Locate the `fetchItineraries` function (around line 100-140)
    - After existing "Upcoming" → "Active" logic, add logic to check if "Active" itineraries should transition to "Completed"
    - Find return flight date and compare to current date
    - If return date has passed, update status to "Completed"
    - Fire PATCH request to update status on server
    - _Bug_Condition: isBugCondition2(itinerary, currentTime) where status is "Active" AND currentTime >= endDate_
    - _Expected_Behavior: Itinerary status automatically transitions from "Active" to "Completed" when return date passes_
    - _Preservation: Existing "Upcoming" → "Active" transition continues to work; manual status updates via builder remain functional_
    - _Requirements: 1.2, 2.2, 3.2_

  - [x] 4.2 Test status transitions with various dates
    - Create test itinerary with return date in the past
    - Call `fetchItineraries` and verify status transitions to "Completed"
    - Create test itinerary with departure date in the past, return date in future
    - Verify status transitions to "Active"
    - Verify dashboard shows correct status
    - _Requirements: 2.2_

  - [x] 4.3 Verify Bug 2 exploration test now passes
    - **Property 1: Expected Behavior** - Itinerary Status Auto-Updates
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - Run Bug 2 exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms status transitions work)
    - _Requirements: 2.2_

- [x] 5. Fix Bug 3: Ensure activity status computation works correctly

  - [x] 5.1 Verify useActivityStatus hook is used consistently
    - Review `src/app/view/[id]/page.tsx` component `TimelineActivityCard`
    - Confirm the component uses computed status from `useActivityStatus` hook for display
    - Verify database status is only used for disruption check (`activity.status === 'issue'`)
    - Ensure time-based statuses ("upcoming", "current", "completed") are NOT persisted to database
    - _Bug_Condition: isBugCondition3(activity, currentTime) where database status does NOT reflect time-based state_
    - _Expected_Behavior: Activity status is computed dynamically based on current time vs. startTime/endTime_
    - _Preservation: Manual status updates (like 'issue') continue to be persisted; existing activity CRUD operations work_
    - _Requirements: 1.3, 2.3, 3.3_

  - [x] 5.2 Ensure builder form doesn't set time-based status
    - Review builder form and API endpoints
    - Verify that when creating/updating activities, time-based statuses are not automatically set
    - Only manual status changes (like 'issue') should be persisted
    - _Requirements: 2.3, 3.3_

  - [x] 5.3 Test activity status computation at different times
    - Create activity with startTime in past, endTime in future
    - Render TimelineActivityCard and verify displayed status is "current"
    - Create activity with endTime in past
    - Verify displayed status is "completed"
    - Verify database status field is not updated
    - _Requirements: 2.3_

  - [x] 5.4 Verify Bug 3 exploration test still passes
    - **Property 1: Expected Behavior** - Activity Status Computation
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - Run Bug 3 exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms status computation works correctly)
    - _Requirements: 2.3_

- [x] 6. Fix Bug 4: Add toast notifications for issue reporting

  - [x] 6.1 Install toast notification library
    - Run `npm install sonner` to add toast library
    - Verify installation in package.json
    - _Requirements: 1.4, 2.4_

  - [x] 6.2 Add Toaster component to root layout
    - Edit `src/app/layout.tsx`
    - Import `Toaster` from 'sonner'
    - Add `<Toaster position="top-right" />` to root layout
    - Verify Toaster renders without errors
    - _Requirements: 2.4_

  - [x] 6.3 Replace browser alert with toast notification
    - Edit `src/app/view/[id]/page.tsx`
    - Import `toast` from 'sonner'
    - Locate `handleDisruptionSubmit` function (around line 242)
    - Replace `alert()` call with `toast.success()` for successful submission
    - Add `toast.error()` for failed submission
    - Include descriptive message and 4-second duration
    - _Bug_Condition: isBugCondition4(userAction, uiState) where visual feedback is null after issue report_
    - _Expected_Behavior: User sees toast notification confirming issue report submission_
    - _Preservation: DisruptionModal submission flow preserves existing API call structure_
    - _Requirements: 1.4, 2.4, 3.4_

  - [x] 6.4 Test toast notifications
    - Open itinerary view page
    - Click "Report Issue" on an activity
    - Submit disruption report
    - Verify toast notification appears with success message
    - Verify toast disappears after 4 seconds
    - Test error scenario and verify error toast appears
    - _Requirements: 2.4_

  - [x] 6.5 Verify Bug 4 exploration test now passes
    - **Property 1: Expected Behavior** - Issue Report Visual Feedback
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - Run Bug 4 exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms toast notifications work)
    - _Requirements: 2.4_

- [x] 7. Fix Bug 5: Add dashboard notifications for disruptions

  - [x] 7.1 Update AttentionItem interface
    - Edit `src/components/dashboard/OpsPanel.tsx`
    - Locate `AttentionItem` interface (around line 88)
    - Add `timestamp?: string` field
    - Add `isRecent?: boolean` field
    - _Requirements: 1.5, 2.5_

  - [x] 7.2 Update buildAttentionList function
    - Locate `buildAttentionList` function (around line 90)
    - Add logic to calculate if disruption is recent (within last 24 hours)
    - Extract timestamp from `itinerary.updatedAt` field
    - Add `timestamp` and `isRecent` to AttentionItem objects
    - Sort items: recent disruptions first, then by dot color
    - _Bug_Condition: isBugCondition5(itinerary, dashboardState) where dashboard does NOT highlight disrupted itinerary prominently_
    - _Expected_Behavior: Dashboard shows notification badge, highlights itinerary with red dot, shows timestamp_
    - _Preservation: Dashboard filtering and search functionality remain unchanged_
    - _Requirements: 1.5, 2.5, 3.5_

  - [x] 7.3 Update NeedsAttentionCard render
    - Locate `NeedsAttentionCard` component render (around line 150)
    - Add "NEW" badge for recent disruptions
    - Add timestamp display after issue description
    - Add pulse animation to red dot for recent disruptions
    - Style "NEW" badge with red background
    - _Requirements: 2.5_

  - [x] 7.4 Test dashboard notifications
    - Create itinerary with status "Disrupted" and recent updatedAt timestamp
    - Open dashboard (OpsPanel)
    - Verify "Needs Attention" panel shows the itinerary
    - Verify "NEW" badge appears for recent disruptions
    - Verify timestamp is displayed
    - Verify red dot has pulse animation
    - Verify sorting places recent disruptions first
    - _Requirements: 2.5_

  - [x] 7.5 Verify Bug 5 exploration test now passes
    - **Property 1: Expected Behavior** - Dashboard Notifications
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - Run Bug 5 exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms dashboard notifications work)
    - _Requirements: 2.5_

- [x] 8. Verify all preservation tests still pass
  - **Property 2: Preservation** - Existing Functionality Preservation
  - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
  - Run all preservation property tests from step 2
  - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
  - Verify map rendering works for valid coordinates
  - Verify manual status updates via builder work
  - Verify CRUD operations preserve data integrity
  - Verify dashboard filtering and search work
  - Verify UI interactions work correctly
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

## Phase 4: Final Validation

- [x] 9. Checkpoint - Ensure all tests pass and all bugs are fixed
  - Run all exploration tests and verify they pass
  - Run all preservation tests and verify they pass
  - Manually test each bug fix:
    - Bug 1: Verify map markers are distinct and accurate
    - Bug 2: Verify itinerary status transitions work automatically
    - Bug 3: Verify activity status is computed correctly
    - Bug 4: Verify toast notifications appear for issue reports
    - Bug 5: Verify dashboard shows notifications for disruptions
  - Verify no regressions in existing functionality
  - Ask the user if questions arise or if any issues are found
  - _Requirements: All requirements (1.1-3.5)_
