---
name: feature-architecting
description: Architects and implements new app features from logic-based requirements with precision. Use when the user asks to "add a feature", "build new functionality", "implement a requirement", "create a module", or needs help translating business logic into clean, maintainable code.
---

# Feature Architecting

## When to use this skill

- User asks to add a new feature to an existing app
- User provides business logic or functional requirements to implement
- User mentions "build a feature", "add functionality", or "implement requirement"
- User needs help translating product specs into technical implementation
- User wants to ensure a feature integrates properly with existing codebase

## Core Philosophy

Features should be:
- **Accurate**: Precisely match the stated requirements
- **Integrated**: Seamlessly fit into existing architecture
- **Maintainable**: Follow project conventions and patterns
- **Tested**: Include verification of core functionality
- **Documented**: Clear purpose and usage instructions

## Feature Development Workflow

### Phase 1: Requirements Analysis

Before writing any code, clarify:

1. **Core Functionality**
   - What is the primary user action or business need?
   - What are the inputs and expected outputs?
   - What edge cases or error scenarios exist?

2. **Integration Points**
   - Which existing modules/components will this interact with?
   - What data structures or APIs need to be accessed?
   - Are there authentication, authorization, or permission requirements?

3. **Success Criteria**
   - How will you verify the feature works correctly?
   - What specific behaviors must be demonstrated?

**Ask the user to confirm these points before proceeding if anything is unclear.**

### Phase 2: Architecture Planning

Create a technical plan covering:

#### File Structure
```markdown
- [ ] Identify files to create (new components, services, utilities)
- [ ] Identify files to modify (existing routes, configs, integrations)
- [ ] Plan folder organization (feature-based vs. layer-based)
```

#### Data Flow
- Define the data model (types, interfaces, schemas)
- Map the flow: User Action → Frontend → Backend → Database → Response
- Identify state management needs (local, global, cached)

#### Dependencies
- New packages or libraries needed
- Existing utilities to reuse
- Configuration changes required

### Phase 3: Implementation

Follow this systematic approach:

1. **Foundation First**
   - Create type definitions/interfaces
   - Set up data models and schemas
   - Add configuration entries

2. **Core Logic**
   - Implement business logic in isolated, testable functions
   - Keep functions pure when possible (predictable, no side effects)
   - Handle errors gracefully with clear messages

3. **Integration**
   - Connect backend APIs/services
   - Wire up frontend components
   - Add routing or navigation as needed

4. **User Interface** (if applicable)
   - Build UI components using existing design system
   - Ensure responsive and accessible design
   - Add loading states and error handling

### Phase 4: Verification

Always verify the feature works:

```markdown
- [ ] Run the application locally
- [ ] Test the happy path (expected user flow)
- [ ] Test edge cases and error scenarios
- [ ] Verify integration with existing features
- [ ] Check console for warnings or errors
```

**Use browser_subagent or run_command to demonstrate the feature working.**

## Code Quality Standards

### Separation of Concerns

Organize code by responsibility:

- **Presentation Layer**: UI components, styling, user interactions
- **Business Logic Layer**: Core algorithms, calculations, transformations
- **Data Layer**: API calls, database queries, data fetching
- **Utility Layer**: Reusable helpers, formatters, validators

### Naming Conventions

Use clear, descriptive names:

```typescript
// ✅ Good: Intent is clear
function calculateUserSubscriptionTier(user: User): SubscriptionTier

// ❌ Bad: Vague or abbreviated
function calcTier(u: any)
```

### Error Handling

Always handle errors explicitly:

```typescript
try {
  const result = await fetchUserData(userId);
  return processData(result);
} catch (error) {
  logger.error('Failed to fetch user data', { userId, error });
  throw new UserDataError('Unable to retrieve user information');
}
```

### Type Safety

- Use TypeScript interfaces or types for all data structures
- Avoid `any` types; use `unknown` if type is truly dynamic
- Define API response types for external data

## Integration Patterns

### Adding to Existing Routes

When extending existing endpoints:

1. Check current route structure and naming patterns
2. Add new routes following the same conventions
3. Update route documentation or API specs
4. Test that existing routes still work

### Modifying Shared Components

When changing reusable components:

1. Identify all usages of the component
2. Ensure changes are backward compatible OR update all usages
3. Add optional props instead of changing existing ones when possible
4. Test in multiple contexts where the component is used

### Database Migrations

When adding new data requirements:

1. Create migration files following project conventions
2. Include both `up` and `down` migrations
3. Test migrations on a development database first
4. Document any data transformations or seeding needed

## Common Feature Types

### CRUD Features

For Create, Read, Update, Delete functionality:

```markdown
1. Define data model (schema, validations)
2. Create database layer (queries, ORM models)
3. Build API endpoints (RESTful or GraphQL)
4. Implement frontend forms and displays
5. Add authorization checks
```

### Integration Features

For third-party service integrations:

```markdown
1. Research API documentation and authentication
2. Create service wrapper/client
3. Add environment configuration (API keys, endpoints)
4. Implement error handling and retries
5. Add request/response logging
```

### Background Job Features

For async processing or scheduled tasks:

```markdown
1. Choose job queue system (existing or new)
2. Define job payload structure
3. Implement worker/processor function
4. Add job scheduling or triggering logic
5. Monitor execution and handle failures
```

## Checklist Template

Copy and update this checklist when implementing a feature:

```markdown
## Feature: [Feature Name]

### Analysis
- [ ] Requirements clearly understood
- [ ] Integration points identified
- [ ] Success criteria defined

### Planning
- [ ] File structure planned
- [ ] Data flow mapped
- [ ] Dependencies identified

### Implementation
- [ ] Types/interfaces created
- [ ] Core logic implemented
- [ ] API integration complete
- [ ] UI components built (if applicable)
- [ ] Error handling added

### Verification
- [ ] Application runs without errors
- [ ] Happy path tested
- [ ] Edge cases handled
- [ ] Integration verified
```

## Anti-Patterns to Avoid

- **Big Ball of Mud**: Breaking changes across many unrelated files
  - *Solution*: Plan minimal change surface; use adapters/facades
  
- **Copy-Paste Programming**: Duplicating code instead of extracting shared logic
  - *Solution*: Create reusable utilities or shared components
  
- **Magic Numbers**: Hard-coding values without explanation
  - *Solution*: Use named constants with descriptive names
  
- **Silent Failures**: Catching errors without logging or user feedback
  - *Solution*: Log errors and provide user-friendly messages
  
- **Premature Optimization**: Complicating code for performance before measuring
  - *Solution*: Build correct first, optimize later with profiling

## Resources

For complex features, create supporting documentation in the feature directory:

- `FEATURE_SPEC.md`: Detailed requirements and acceptance criteria
- `ARCHITECTURE.md`: Technical design decisions and diagrams
- `TESTING.md`: Test scenarios and validation steps

## Example Workflow

**User Request**: "Add a password reset feature to the user authentication system"

**Your Response**:

1. **Analyze**: 
   - User clicks "Forgot Password" → enters email → receives reset link → clicks link → sets new password
   - Needs: email service, token generation, database storage, UI forms
   - Success: User can reset password and log in with new credentials

2. **Plan**:
   ```
   Backend:
   - Create /auth/forgot-password endpoint (generates token, sends email)
   - Create /auth/reset-password endpoint (validates token, updates password)
   - Add resetToken and resetTokenExpiry to User model
   
   Frontend:
   - ForgotPasswordForm component (email input)
   - ResetPasswordForm component (new password input)
   - Update login page with "Forgot Password" link
   ```

3. **Implement**: [Create files systematically following the plan]

4. **Verify**: Test full flow with browser_subagent, showing screenshots of each step

## Key Principles

- **Understand before building**: Never code without clear requirements
- **Plan before implementing**: Architecture prevents technical debt
- **Test as you build**: Verify incrementally, not just at the end
- **Document your decisions**: Future maintainers (including you) will thank you
- **Ask when uncertain**: Clarifying now saves refactoring later
