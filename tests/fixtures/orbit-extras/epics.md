# Orbit-extras - Epics and Stories

## Overview

A second synthetic sprint that reuses the numbers of the first one (Epic 1, Story 1.1), in English headings.

## Requirements inventory

### Functional requirements

| ID | Description |
|---|---|
| FR-X-1 | Build a manifest of the parts of a ship |

## Coverage map

FR-X-1 → Epic 1.

## Epic 1: Detect and build the manifest

**Goal:** detect and build the manifest for the travellers of Orbit-extras.

**Depends on:** nothing.

### Story 1.1: Read the dependency files

**As a** traveller,
**I want** to read the dependency files,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Read the dependency files" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 1.2: Build the manifest document

**As a** traveller,
**I want** to build the manifest document,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Build the manifest document" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 1.3: Handle the edge cases

**As a** traveller,
**I want** to handle the edge cases,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Handle the edge cases" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Epic 2: Match against advisories

**Goal:** match against advisories for the travellers of Orbit-extras.

**Depends on:** epic 1.

### Story 2.1: Match components and advisories

**As a** traveller,
**I want** to match components and advisories,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Match components and advisories" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 2.2: Protect the automatic closing

**As a** traveller,
**I want** to protect the automatic closing,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Protect the automatic closing" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Epic 3: Export and governance

**Goal:** export and governance for the travellers of Orbit-extras.

**Depends on:** epic 2.

### Story 3.1: Export a dated manifest

**As a** traveller,
**I want** to export a dated manifest,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Export a dated manifest" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 3.2: Journal each manifest

**As a** traveller,
**I want** to journal each manifest,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Journal each manifest" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

### Story 3.3: Test and quality

**As a** traveller,
**I want** to test and quality,
**So that** the trip stays easy to follow.

**Acceptance criteria:**

- **AC-1:** "Test and quality" works for a valid request.
- **AC-2:** An invalid request is refused with a message that says why.
- **AC-3:** Doing it twice changes nothing the second time.

---

## Decisions made

- The manifest is written in one format only.

## Open debts

None.
