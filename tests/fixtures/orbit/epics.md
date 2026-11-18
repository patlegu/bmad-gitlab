---
status: draft
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories"]
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
---

# Orbit - Epics and Stories

## Overview

A synthetic epics file: invented, in the shape of a real one (French headings, a requirements part before the
epics, two parts after them).

## Requirements inventory

### Functional requirements

| ID | Description |
|---|---|
| FR-1 | List the planets of a system |
| FR-2 | Book a trip |

### Non-functional requirements

| ID | Description |
|---|---|
| NFR-1 | Keep a journal that is never rewritten |

## Coverage map

FR-1 → Epic 1; FR-2 → Epic 2.

## Épique 1 : Planets and catalogue

**Goal:** planets and catalogue for the travellers of Orbit.

**Depends on:** nothing.

### Story 1.1 : Plan a café stop

**As a** traveller,
**I want** to plan a café stop,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Plan a café stop" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 1.2 : List the planets

**As a** traveller,
**I want** to list the planets,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "List the planets" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 1.3 : Show one planet

**As a** traveller,
**I want** to show one planet,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Show one planet" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 1.4 : Search by distance

**As a** traveller,
**I want** to search by distance,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Search by distance" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 2 : Trip booking

**Goal:** trip booking for the travellers of Orbit.

**Depends on:** epic 1.

### Story 2.1 : Book a trip

**As a** traveller,
**I want** to book a trip,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Book a trip" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 2.2 : Cancel a trip

**As a** traveller,
**I want** to cancel a trip,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Cancel a trip" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 2.3 : Change the date

**As a** traveller,
**I want** to change the date,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Change the date" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 3 : Crew and ships

**Goal:** crew and ships for the travellers of Orbit.

**Depends on:** epic 2.

### Story 3.1 : Assign a crew

**As a** traveller,
**I want** to assign a crew,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Assign a crew" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 3.2 : Check the ship

**As a** traveller,
**I want** to check the ship,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Check the ship" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 3.3 : Refuel at a station

**As a** traveller,
**I want** to refuel at a station,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Refuel at a station" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 4 : Safety checks

**Goal:** safety checks for the travellers of Orbit.

**Depends on:** epic 3.

### Story 4.1 : Run the pre-flight list

**As a** traveller,
**I want** to run the pre-flight list,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Run the pre-flight list" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 4.2 : Report an incident

**As a** traveller,
**I want** to report an incident,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Report an incident" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 4.3 : Close an incident

**As a** traveller,
**I want** to close an incident,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Close an incident" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 5 : Payments

**Goal:** payments for the travellers of Orbit.

**Depends on:** epic 4.

### Story 5.1 : Pay by card

**As a** traveller,
**I want** to pay by card,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Pay by card" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 5.2 : Refund a trip

**As a** traveller,
**I want** to refund a trip,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Refund a trip" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 6 : Notifications

**Goal:** notifications for the travellers of Orbit.

**Depends on:** epic 5.

### Story 6.1 : Send a booking mail

**As a** traveller,
**I want** to send a booking mail,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Send a booking mail" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 6.2 : Send a reminder

**As a** traveller,
**I want** to send a reminder,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Send a reminder" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 6.3 : Choose the channel

**As a** traveller,
**I want** to choose the channel,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Choose the channel" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Épique 7 : Quality and governance

**Goal:** quality and governance for the travellers of Orbit.

**Depends on:** epic 6.

### Story 7.1 : Keep the journal append-only

**As a** traveller,
**I want** to keep the journal append-only,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Keep the journal append-only" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 7.2 : Write readable errors

**As a** traveller,
**I want** to write readable errors,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Write readable errors" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 7.3 : Keep secrets out of the repository

**As a** traveller,
**I want** to keep secrets out of the repository,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Keep secrets out of the repository" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 7.4 : Write in plain English

**As a** traveller,
**I want** to write in plain English,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Write in plain English" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 7.5 : Hold the coverage floor

**As a** traveller,
**I want** to hold the coverage floor,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Hold the coverage floor" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 7.6 : Prove each guard by mutation

**As a** traveller,
**I want** to prove each guard by mutation,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Prove each guard by mutation" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Open debts

| ID | Debt | Epic | Priority |
|---|---|---|---|
| D1 | Only one currency is handled | Epic 5 | Medium |

---

## Open questions

| # | Question | Epic |
|---|---|---|
| Q1 | Which payment provider? | Epic 5 |
