# Hemaya – Comprehensive QA Test Cases
**Platform:** AI-Powered Compliance Intelligence (B2B SaaS)  
**Stack:** React 18 + Vite · FastAPI · PostgreSQL (Supabase) · OpenAI  
**Date:** 2026-05-08  
**Total Test Cases:** 162  

---

## Legend
| Field | Values |
|-------|--------|
| **Priority** | High / Medium / Low |
| **Severity** | Critical / Major / Minor / Trivial |
| **Type** | Functional · UI · API · Security · Performance · E2E · Regression · Validation |

---

## Module Index
1. [Authentication – Login](#1-authentication--login)
2. [Authentication – Signup](#2-authentication--signup)
3. [Authentication – OTP Verification](#3-authentication--otp-verification)
4. [Authentication – Forgot Password](#4-authentication--forgot-password)
5. [Landing Page](#5-landing-page)
6. [Home Page](#6-home-page-home)
7. [Dashboard](#7-dashboard-dashboard)
8. [Policy Management](#8-policy-management-policies)
9. [Compliance Analyses](#9-compliance-analyses-analyses)
10. [Frameworks](#10-frameworks-frameworks)
11. [Gaps & Risks](#11-gaps--risks-gapsrisks)
12. [Mapping Review](#12-mapping-review-mappingreview)
13. [Explainability](#13-explainability-explainability)
14. [AI Insights](#14-ai-insights-aiinsights)
15. [AI Assistant (Chatbot)](#15-ai-assistant-aiassistant)
16. [Simulation](#16-simulation-simulation)
17. [Reports](#17-reports-reports)
18. [Settings / Profile](#18-settings--profile-settings)
19. [Admin Panel](#19-admin-panel-admin)
20. [UI / UX](#20-uiux-test-cases)
21. [Cross-Browser & Responsive](#21-cross-browser--responsive)
22. [Performance](#22-performance)
23. [Security](#23-security)
24. [API](#24-api-test-cases)
25. [End-to-End Journeys](#25-end-to-end-user-journeys)
26. [Regression](#26-regression)
27. [Automation Recommendations](#27-automation-recommendations)

---

## 1. Authentication – Login

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-AUTH-001 | Login | Valid login with correct credentials | User registered and OTP-verified | 1. Go to `/login` 2. Enter valid email 3. Enter correct password 4. Click Login | Email: `user@hemaya.sa` Password: `Test@1234` | Redirected to `/Home`; JWT stored in `localStorage`; user name shown in header | High | Critical | Functional |
| TC-AUTH-002 | Login | Login with wrong password | User registered | 1. Go to `/login` 2. Enter valid email 3. Enter wrong password 4. Click Login | Email: `user@hemaya.sa` Password: `WrongPass` | Error toast "Invalid credentials"; no redirect; no token stored | High | Critical | Functional |
| TC-AUTH-003 | Login | Login with non-existent email | None | 1. Go to `/login` 2. Enter unregistered email 3. Click Login | Email: `ghost@test.com` | Error shown; no redirect | High | Major | Functional |
| TC-AUTH-004 | Login | Login with both fields empty | None | 1. Go to `/login` 2. Leave fields empty 3. Click Login | — | Validation errors on both fields; no API call | High | Major | Validation |
| TC-AUTH-005 | Login | Login with invalid email format | None | 1. Enter `notanemail` in email field 2. Click Login | Email: `notanemail` | Email format validation error | Medium | Minor | Validation |
| TC-AUTH-006 | Login | Accessing protected route without auth | Not logged in | 1. Navigate directly to `/Dashboard` | — | Redirected to `/login` | High | Critical | Functional |
| TC-AUTH-007 | Login | Session persists after browser refresh | User logged in | 1. Login 2. Refresh page | — | User remains logged in (token in `localStorage`) | Medium | Major | Functional |
| TC-AUTH-008 | Login | Admin login grants admin access | Admin account | 1. Login with `himayaadmin@gmail.com` | Admin credentials | `/admin` route accessible; admin UI shown | High | Critical | Functional |
| TC-AUTH-009 | Login | Regular user cannot access `/admin` | Regular user logged in | 1. Login as non-admin 2. Navigate to `/admin` | Regular credentials | Redirected away or shown 403/Unauthorized UI | High | Critical | Security |
| TC-AUTH-010 | Login | Inactivity logout after timeout | User logged in, session timeout configured | 1. Login 2. Leave idle past timeout | Timeout: 30 min (admin-set) | User auto-logged out; redirected to `/login` | High | Major | Functional |

---

## 2. Authentication – Signup

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-SIGNUP-001 | Signup | Successful registration | Email not in DB | 1. Go to `/signup` 2. Fill all fields 3. Submit | First: `Jana`, Last: `Al-Rashid`, Phone: `0512345678`, Email: `jana@test.sa`, Pass: `Test@1234` | OTP email sent; redirected to `/verify-otp` | High | Critical | Functional |
| TC-SIGNUP-002 | Signup | Duplicate email rejected | Email already registered | 1. Use existing email in signup | Email: existing | Error "Email already in use"; no OTP sent | High | Major | Functional |
| TC-SIGNUP-003 | Signup | Invalid phone format | None | 1. Enter phone not matching `05xxxxxxxx` | Phone: `123456789` | Validation error: invalid Saudi phone format | High | Major | Validation |
| TC-SIGNUP-004 | Signup | Valid Saudi phone accepted | None | 1. Enter `0512345678` | Phone: `0512345678` | No phone validation error | Medium | Minor | Validation |
| TC-SIGNUP-005 | Signup | Password shorter than 8 chars | None | 1. Enter short password | Pass: `abc123` | Validation error: minimum 8 characters | High | Major | Validation |
| TC-SIGNUP-006 | Signup | All required fields empty on submit | None | 1. Click Submit with no input | — | Validation errors on all required fields | High | Major | Validation |
| TC-SIGNUP-007 | Signup | Password strength indicator responds to input | None | 1. Type increasingly complex passwords | `12345678` → `Test@1234!` | Strength meter updates from Weak → Strong | Medium | Minor | UI |
| TC-SIGNUP-008 | Signup | Special characters in name fields | None | 1. Enter `<script>` as first name | Name: `<script>alert(1)</script>` | Input sanitized or validation error; no XSS executed | High | Critical | Security |
| TC-SIGNUP-009 | Signup | Very long email (255+ chars) | None | 1. Enter 300-char email | Long email | Validation error or graceful rejection | Medium | Minor | Validation |

---

## 3. Authentication – OTP Verification

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-OTP-001 | OTP | Correct OTP verifies account | User registered, OTP received | 1. Go to `/verify-otp` 2. Enter correct OTP 3. Submit | Correct OTP from email | Account verified; redirected to `/login` | High | Critical | Functional |
| TC-OTP-002 | OTP | Incorrect OTP rejected | User registered | 1. Enter wrong OTP 2. Submit | OTP: `000000` | Error "Invalid OTP"; account not verified | High | Major | Functional |
| TC-OTP-003 | OTP | Resend OTP sends new code | User on `/verify-otp` | 1. Click Resend OTP | — | New OTP delivered to email; success message shown | Medium | Major | Functional |
| TC-OTP-004 | OTP | Expired OTP rejected | OTP expired | 1. Wait for expiry 2. Enter expired OTP | Expired OTP | Error "OTP expired"; user prompted to resend | High | Major | Functional |
| TC-OTP-005 | OTP | OTP cannot be reused | OTP already verified | 1. Verify with OTP 2. Try same OTP again | Same OTP | Second use rejected with error | High | Critical | Security |

---

## 4. Authentication – Forgot Password

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-FP-001 | ForgotPassword | Request reset for registered email | User registered | 1. Go to `/forgot-password` 2. Enter valid email 3. Submit | Email: `user@hemaya.sa` | OTP sent; generic success message (no user enumeration) | High | Critical | Functional |
| TC-FP-002 | ForgotPassword | Request reset for unregistered email | None | 1. Enter unregistered email | Email: `ghost@test.com` | Same generic message as TC-FP-001 (no enumeration leak) | High | Major | Security |
| TC-FP-003 | ForgotPassword | Reset with valid OTP and new password | Reset OTP received | 1. Enter correct OTP 2. Enter new password (8+ chars) 3. Submit | OTP: correct, NewPass: `NewTest@5678` | Password updated; redirected to `/login`; new password works | High | Critical | Functional |
| TC-FP-004 | ForgotPassword | Reset with weak new password | OTP received | 1. Enter short new password | NewPass: `1234` | Validation error: min 8 characters | Medium | Major | Validation |
| TC-FP-005 | ForgotPassword | Reset with expired OTP | OTP expired | 1. Enter expired OTP | Expired OTP | Error: OTP expired | High | Major | Functional |

---

## 5. Landing Page

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-LAND-001 | Landing | All sections render correctly | None | 1. Navigate to `/` | — | Hero, Features, Workflow, Frameworks sections all visible | High | Major | UI |
| TC-LAND-002 | Landing | CTA "Get Started" navigates to signup | None | 1. Click Get Started | — | Navigated to `/signup` | High | Major | Functional |
| TC-LAND-003 | Landing | "Login" link navigates to login | None | 1. Click Login | — | Navigated to `/login` | High | Major | Functional |
| TC-LAND-004 | Landing | Dark mode toggle switches theme | None | 1. Click dark mode toggle | — | Theme switches; persists on page refresh | Medium | Minor | UI |
| TC-LAND-005 | Landing | Logged-in user accessing `/` | User logged in | 1. Navigate to `/` | Valid session | Either redirected to `/Home` or landing shown per design intent | Medium | Minor | Functional |
| TC-LAND-006 | Landing | Page is responsive on mobile | None | 1. View at 375px width | — | No horizontal overflow; text readable | High | Major | UI |

---

## 6. Home Page (`/Home`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-HOME-001 | Home | Welcome message shows user's name | User logged in | 1. Navigate to `/Home` | — | User's first name displayed in greeting | Medium | Minor | UI |
| TC-HOME-002 | Home | Quick action "Upload Policy" navigates correctly | User logged in | 1. Click Upload Policy quick action | — | Navigated to `/Policies` | High | Major | Functional |
| TC-HOME-003 | Home | Recent policies list loads | User has uploaded policies | 1. Navigate to `/Home` | — | Policies listed with name, status badge, date | High | Major | Functional |
| TC-HOME-004 | Home | Empty state when no policies exist | New user | 1. Navigate to `/Home` | — | Empty state UI with CTA to upload first policy | Medium | Minor | UI |
| TC-HOME-005 | Home | Status badges display correct colors | Policies with various statuses | 1. View policies list | — | Processing=yellow, Analyzed=green, Failed=red | Medium | Minor | UI |

---

## 7. Dashboard (`/Dashboard`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-DASH-001 | Dashboard | KPI cards load with correct values | User has analyzed policies | 1. Navigate to `/Dashboard` | — | Total Policies, Compliance Score, Gaps, Analyses all show correct numbers | High | Critical | Functional |
| TC-DASH-002 | Dashboard | Bar/Pie charts render without errors | User has data | 1. Navigate to `/Dashboard` | — | Recharts graphs render; no console errors | High | Major | UI |
| TC-DASH-003 | Dashboard | Status filter "Analyzed" shows only analyzed | Policies in various statuses | 1. Select "Analyzed" filter | — | Only analyzed policies appear in list | High | Major | Functional |
| TC-DASH-004 | Dashboard | Status filter "Processing" | Policies processing | 1. Select "Processing" filter | — | Only processing policies shown | High | Major | Functional |
| TC-DASH-005 | Dashboard | Empty state for new user | No policies | 1. Navigate to `/Dashboard` as new user | — | Zero-state UI; no broken charts or errors | Medium | Minor | UI |
| TC-DASH-006 | Dashboard | Real-time stats update without page refresh | Policy processing | 1. Open Dashboard 2. Wait 2+ seconds | — | KPI values update automatically (2s polling) | High | Major | Functional |
| TC-DASH-007 | Dashboard | Clicking policy row navigates to detail | Policies exist | 1. Click on a policy in the list | — | Navigates to analysis detail page | Medium | Minor | Functional |
| TC-DASH-008 | Dashboard | Skeleton loaders shown during fetch | Slow connection simulated | 1. Open Dashboard on throttled network | — | Skeleton placeholders shown before data loads | Medium | Minor | UI |

---

## 8. Policy Management (`/Policies`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-POL-001 | Policies | Upload valid PDF and start analysis | User logged in | 1. Go to `/Policies` 2. Click Upload 3. Select PDF 4. Choose framework 5. Submit | `policy.pdf` · Framework: ISO 27001 | Upload succeeds; policy appears with "Processing" status | High | Critical | Functional |
| TC-POL-002 | Policies | Upload valid DOCX file | User logged in | Same as TC-POL-001 with DOCX | `policy.docx` | Upload succeeds | High | Critical | Functional |
| TC-POL-003 | Policies | Upload XLS file | User logged in | Upload `.xls` file | `controls.xls` | Upload succeeds if supported; error if not | Medium | Major | Functional |
| TC-POL-004 | Policies | Upload unsupported file type | User logged in | 1. Upload `.exe` file | `malware.exe` | Error: "Unsupported file type"; no upload | High | Critical | Validation |
| TC-POL-005 | Policies | Upload without selecting framework | User logged in | 1. Upload file without framework selection | PDF only | Validation error: framework required | High | Major | Validation |
| TC-POL-006 | Policies | Progress bar tracks analysis 0→100% | Policy uploaded | 1. Watch progress bar during analysis | — | Progress increments with correct stage labels | High | Major | UI |
| TC-POL-007 | Policies | Pause analysis mid-process | Policy being analyzed | 1. Click Pause during analysis | — | Analysis pauses; status shows "Paused" | High | Major | Functional |
| TC-POL-008 | Policies | Resume paused analysis | Policy in "Paused" state | 1. Click Resume | — | Analysis resumes from last checkpoint | High | Major | Functional |
| TC-POL-009 | Policies | Delete policy shows confirmation dialog | Policy exists | 1. Click Delete on policy | — | Confirmation modal appears | High | Major | UI |
| TC-POL-010 | Policies | Cancel deletion keeps policy | Policy exists | 1. Click Delete 2. Click Cancel in dialog | — | Policy NOT deleted | High | Major | Functional |
| TC-POL-011 | Policies | Confirm deletion removes policy | Policy exists | 1. Click Delete 2. Confirm | — | Policy removed from list; success toast | High | Major | Functional |
| TC-POL-012 | Policies | Upload empty/zero-byte file | User logged in | 1. Upload 0-byte file | `empty.pdf` | Error shown; graceful failure; no crash | High | Major | Validation |
| TC-POL-013 | Policies | Upload large file (15MB+) | User logged in | 1. Upload 15MB PDF | `large.pdf` (15MB) | Upload completes or shows clear file-size error | Medium | Major | Performance |
| TC-POL-014 | Policies | Multiple concurrent uploads | User logged in | 1. Upload 3 policies in succession | 3 different PDFs | All 3 appear independently; each processes separately | Medium | Major | Functional |
| TC-POL-015 | Policies | Polling stops after analysis completes | Policy finished | 1. Wait for analysis to finish | — | "Analyzed" status shown; polling stops (no continuous calls) | Medium | Minor | Functional |

---

## 9. Compliance Analyses (`/Analyses`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-ANA-001 | Analyses | Analysis results load for analyzed policy | Policy analyzed | 1. Go to `/Analyses` 2. Select policy | — | Compliance score, mapped controls, gap count shown | High | Critical | Functional |
| TC-ANA-002 | Analyses | Filter results by framework NCA ECC | Multiple frameworks analyzed | 1. Apply "NCA ECC" filter | — | Only NCA ECC results shown | High | Major | Functional |
| TC-ANA-003 | Analyses | Drill down into a control | Results available | 1. Click on a control item | — | Control name, evidence, confidence score shown | High | Major | Functional |
| TC-ANA-004 | Analyses | Compliance score color-coded correctly | Analysis done | 1. View score | — | High score=green, medium=yellow, low=red | Medium | Minor | UI |
| TC-ANA-005 | Analyses | Empty state when no analyses | New user | 1. Navigate to `/Analyses` | — | Empty state with CTA to upload a policy | Medium | Minor | UI |
| TC-ANA-006 | Analyses | Controls count matches DB | Analysis done | 1. View controls count on page | — | Number matches actual controls in DB | High | Major | Functional |

---

## 10. Frameworks (`/Frameworks`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-FW-001 | Frameworks | All 3 frameworks listed | Frameworks loaded in DB | 1. Navigate to `/Frameworks` | — | NCA ECC 2024, ISO 27001, NIST 800-53 all listed | High | Major | Functional |
| TC-FW-002 | Frameworks | Framework metadata shown | Frameworks loaded | 1. View framework cards | — | Controls count, coverage %, version number shown | Medium | Minor | UI |
| TC-FW-003 | Frameworks | Empty state when no frameworks | No frameworks in DB | 1. Navigate to `/Frameworks` | — | Friendly empty state shown | Low | Minor | UI |

---

## 11. Gaps & Risks (`/GapsRisks`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-GAP-001 | GapsRisks | All gaps load in table | Gaps exist | 1. Navigate to `/GapsRisks` | — | All gaps shown with severity, status, description, control ID | High | Critical | Functional |
| TC-GAP-002 | GapsRisks | Filter by severity "Critical" | Gaps with various severities | 1. Apply Critical filter | — | Only Critical gaps shown | High | Major | Functional |
| TC-GAP-003 | GapsRisks | Filter by status "Open" | Gaps with various statuses | 1. Apply Open filter | — | Only Open gaps shown | High | Major | Functional |
| TC-GAP-004 | GapsRisks | Search gaps by keyword | Gaps exist | 1. Type keyword in search box | Keyword: `access control` | Matching gaps shown; non-matching hidden | High | Major | Functional |
| TC-GAP-005 | GapsRisks | Assign owner to a gap | Gap exists | 1. Click edit 2. Enter owner name 3. Save | Owner: `Ahmed Al-Rashidi` | Owner saved and shown in table | High | Major | Functional |
| TC-GAP-006 | GapsRisks | Change gap severity | Gap exists | 1. Edit gap 2. Change severity | High → Critical | Severity updated in UI and DB | High | Major | Functional |
| TC-GAP-007 | GapsRisks | Change gap status to "Resolved" | Gap "Open" | 1. Edit gap 2. Set status to Resolved 3. Save | Status: Resolved | Status updated; gap removed from Open filter | High | Major | Functional |
| TC-GAP-008 | GapsRisks | Sort table by severity | Gaps exist | 1. Click Severity column header | — | Gaps sorted ascending then descending on second click | Medium | Minor | UI |
| TC-GAP-009 | GapsRisks | Pagination works with many gaps | 50+ gaps | 1. Navigate pages | — | Each page loads correct subset; no duplicates | Medium | Major | UI |
| TC-GAP-010 | GapsRisks | Empty state when no gaps | Fully compliant policy | 1. Navigate to `/GapsRisks` | — | "No gaps found" message | Medium | Minor | UI |

---

## 12. Mapping Review (`/MappingReview`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-MAP-001 | MappingReview | Mappings list loads | Policy analyzed | 1. Navigate to `/MappingReview` | — | Control mappings shown with confidence scores and evidence | High | Critical | Functional |
| TC-MAP-002 | MappingReview | Accept a mapping | Mappings available | 1. Click Accept on a mapping | — | Mapping marked accepted; visual indicator (green) | High | Critical | Functional |
| TC-MAP-003 | MappingReview | Reject a mapping | Mappings available | 1. Click Reject on a mapping | — | Mapping marked rejected; visual indicator (red) | High | Critical | Functional |
| TC-MAP-004 | MappingReview | Accepted/rejected states persist on refresh | Decisions made | 1. Accept a mapping 2. Refresh page | — | Decision state preserved | High | Major | Functional |
| TC-MAP-005 | MappingReview | Filter by confidence score threshold | Mappings with various scores | 1. Set filter > 0.8 | Threshold: 0.8 | Only high-confidence mappings shown | High | Major | Functional |
| TC-MAP-006 | MappingReview | Evidence snippet expands on click | Mapping row | 1. Click on mapping to expand | — | Evidence text shown; keywords highlighted | High | Major | UI |
| TC-MAP-007 | MappingReview | Empty state if no mappings | No analysis done | 1. Navigate to `/MappingReview` | — | Empty state shown | Medium | Minor | UI |

---

## 13. Explainability (`/Explainability`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-EXP-001 | Explainability | AI rationale shown for a mapping | Mappings exist | 1. Navigate to `/Explainability` 2. Select a mapping | — | AI rationale text, evidence snippet, confidence score all displayed | High | Major | Functional |
| TC-EXP-002 | Explainability | Evidence citation links to source text | Evidence exists | 1. View explanation | — | Cited text from policy shown verbatim | High | Major | Functional |
| TC-EXP-003 | Explainability | Confidence score displayed as numeric | Mapping selected | 1. View confidence | — | Score shown as decimal (e.g., 0.87) or percentage | Medium | Minor | UI |

---

## 14. AI Insights (`/AIInsights`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-INS-001 | AIInsights | Generate insights for a policy | Policy analyzed | 1. Go to `/AIInsights` 2. Select policy 3. Generate | — | Gap priorities, policy improvements, risk alerts, trends shown | High | Critical | Functional |
| TC-INS-002 | AIInsights | Insights labeled by priority | Insights generated | 1. View insights list | — | Each insight tagged High/Medium/Low priority | High | Major | UI |
| TC-INS-003 | AIInsights | Loading skeleton during generation | — | 1. Trigger generation | — | Skeleton/spinner shown; no blank white flash | Medium | Minor | UI |
| TC-INS-004 | AIInsights | Error when OpenAI unavailable | OpenAI API down | 1. Trigger insight generation | — | User-friendly error message; no crash | High | Major | Functional |
| TC-INS-005 | AIInsights | Insights differ between policies | Two different policies | 1. Generate insights for policy A 2. Switch to policy B | — | Different insights per policy | High | Major | Functional |

---

## 15. AI Assistant (`/AIAssistant`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-CHAT-001 | AIAssistant | Send compliance question and receive answer | User logged in | 1. Go to `/AIAssistant` 2. Type question 3. Send | `"What are my top 3 gaps?"` | Relevant AI response received and displayed | High | Critical | Functional |
| TC-CHAT-002 | AIAssistant | Suggested question chips populate input | None | 1. Click a suggested question chip | — | Question text placed in input; sent automatically | Medium | Minor | UI |
| TC-CHAT-003 | AIAssistant | Loading indicator shown during response | — | 1. Send a message | — | Typing indicator / spinner shown while awaiting AI | Medium | Minor | UI |
| TC-CHAT-004 | AIAssistant | Markdown rendered in AI responses | AI returns markdown | 1. Receive response with headers and bullets | — | Markdown rendered (bold, lists, code blocks) | Medium | Minor | UI |
| TC-CHAT-005 | AIAssistant | Chat history persists within session | Active session | 1. Send messages 2. Navigate to Dashboard 3. Return | — | All messages still visible | Medium | Major | Functional |
| TC-CHAT-006 | AIAssistant | Chat history cleared on new session | User logs out and back in | 1. Logout 2. Login again 3. Open AIAssistant | — | Chat history empty (sessionStorage cleared) | Medium | Minor | Functional |
| TC-CHAT-007 | AIAssistant | Empty input not submitted | None | 1. Leave input blank 2. Click Send | — | No message sent; no API call; button possibly disabled | Medium | Minor | Validation |
| TC-CHAT-008 | AIAssistant | 75-second timeout handled gracefully | Slow/unavailable AI | 1. Send message 2. Let it timeout | — | Timeout error message shown; chat still usable | High | Major | Functional |
| TC-CHAT-009 | AIAssistant | Message history capped at 50 messages | User sends 51 messages | 1. Send 51st message | — | Oldest message pruned; session functional | Low | Minor | Functional |

---

## 16. Simulation (`/Simulation`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-SIM-001 | Simulation | Select controls and see projected score | Gaps/controls exist | 1. Go to `/Simulation` 2. Select 5 controls to remediate | 5 controls selected | Projected compliance score shown with delta vs baseline | High | Major | Functional |
| TC-SIM-002 | Simulation | Score delta shows improvement | Controls selected | 1. View simulation result | — | Delta shown (e.g., +12%) in positive color | High | Major | UI |
| TC-SIM-003 | Simulation | Deselect all resets to baseline | Controls selected | 1. Deselect all controls | — | Reverts to baseline score | Medium | Minor | Functional |
| TC-SIM-004 | Simulation | Empty state when no controls | No analysis done | 1. Navigate to `/Simulation` | — | Friendly empty state | Medium | Minor | UI |

---

## 17. Reports (`/Reports`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-REP-001 | Reports | Generate and download PDF report | Policy analyzed | 1. Go to `/Reports` 2. Select policy 3. Choose PDF 4. Generate | Any analyzed policy | PDF file downloaded; opens without errors | High | Critical | Functional |
| TC-REP-002 | Reports | Generate and download CSV report | Policy analyzed | Same as above, choose CSV | Format: CSV | CSV file downloaded with correct columns | High | Major | Functional |
| TC-REP-003 | Reports | Report preview before download | Report generated | 1. Click Preview | — | Report preview shown in modal/preview panel | Medium | Major | UI |
| TC-REP-004 | Reports | PDF contains correct compliance score | PDF downloaded | 1. Open downloaded PDF | — | Score in PDF matches score shown in UI | High | Critical | Functional |
| TC-REP-005 | Reports | PDF contains all gaps | PDF downloaded | 1. Open PDF 2. Check gaps section | — | All gaps listed with severity and status | High | Major | Functional |
| TC-REP-006 | Reports | Saved reports listed | Reports saved | 1. Navigate to `/Reports` | — | Previously saved reports listed with date/format | Medium | Major | Functional |
| TC-REP-007 | Reports | Delete a saved report | Report exists | 1. Click Delete 2. Confirm | — | Report removed from list | Medium | Minor | Functional |
| TC-REP-008 | Reports | Generate report without selecting policy | None | 1. Click Generate without selecting | — | Validation error: policy required | High | Major | Validation |
| TC-REP-009 | Reports | Report branding present | PDF downloaded | 1. Open PDF | — | Hemaya logo/branding present in report | Low | Trivial | UI |

---

## 18. Settings / Profile (`/Settings`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-SET-001 | Settings | Update first name | User logged in | 1. Go to `/Settings` 2. Change first name 3. Save | New name: `Mohammed` | Name updated; shown in header/welcome | High | Major | Functional |
| TC-SET-002 | Settings | Update email address | User logged in | 1. Change email 2. Save | New email: `new@hemaya.sa` | Email updated in profile | High | Major | Functional |
| TC-SET-003 | Settings | Change password – correct current | User logged in | 1. Enter current password 2. Enter new 3. Confirm 4. Save | Current: `Test@1234`, New: `NewPass@5678` | Password changed; success toast | High | Critical | Functional |
| TC-SET-004 | Settings | Change password – wrong current | User logged in | 1. Enter wrong current password | Wrong current | Error: "Incorrect current password" | High | Major | Functional |
| TC-SET-005 | Settings | Change password – mismatch | User logged in | 1. New password ≠ confirm password | New: `Test@1234`, Confirm: `Test@1235` | Error: "Passwords do not match" | High | Major | Validation |
| TC-SET-006 | Settings | Change password – too short new password | User logged in | 1. Enter 5-char new password | New: `abc12` | Validation error: min 8 chars | Medium | Minor | Validation |
| TC-SET-007 | Settings | Profile form shows current user data | User logged in | 1. Open Settings page | — | Current name, email pre-filled in form | Medium | Minor | UI |

---

## 19. Admin Panel (`/admin`)

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-ADM-001 | Admin | All users listed in Users tab | Admin logged in | 1. Go to `/admin` → Users tab | — | All registered users shown with email, role, status | High | Critical | Functional |
| TC-ADM-002 | Admin | Promote user to admin role | Admin logged in | 1. Select user 2. Change role to Admin | User: `test@test.com` | Role updated; user now has admin access | High | Critical | Functional |
| TC-ADM-003 | Admin | Disable a user account | Admin logged in | 1. Click Disable on user | — | User disabled; that user cannot login | High | Critical | Functional |
| TC-ADM-004 | Admin | Re-enable a disabled user | Admin logged in | 1. Click Enable on disabled user | — | User can login again | High | Major | Functional |
| TC-ADM-005 | Admin | Delete user with confirmation | Admin logged in | 1. Click Delete 2. Confirm | — | User removed from system | High | Critical | Functional |
| TC-ADM-006 | Admin | View all policies from all users | Admin logged in | 1. Go to Policies tab | — | Policies from ALL users shown (not just admin's) | High | Major | Functional |
| TC-ADM-007 | Admin | Reanalyze a policy | Admin logged in | 1. Click Reanalyze on a policy | — | Analysis re-triggered; status resets to Processing | High | Major | Functional |
| TC-ADM-008 | Admin | Delete any policy (admin power) | Admin logged in | 1. Delete a policy | — | Policy deleted; success toast | High | Major | Functional |
| TC-ADM-009 | Admin | Add a new framework | Admin logged in | 1. Go to Frameworks tab 2. Click Add 3. Fill details 4. Upload doc | Name: `SAMA CSF v2`, Version: `2.0` | Framework saved and appears in list | High | Major | Functional |
| TC-ADM-010 | Admin | Edit framework metadata | Admin logged in | 1. Edit framework name/version | New version: `2.1` | Updated framework shown | Medium | Major | Functional |
| TC-ADM-011 | Admin | Delete framework | Admin logged in | 1. Delete framework 2. Confirm | — | Framework removed | High | Major | Functional |
| TC-ADM-012 | Admin | View activity logs | Admin logged in | 1. Go to Activity Logs tab | — | Audit trail shown with user, action, timestamp | High | Major | Functional |
| TC-ADM-013 | Admin | Activity log entries for login events | Admin does actions | 1. Perform actions 2. Check logs | — | Each action recorded with correct user and timestamp | High | Major | Functional |
| TC-ADM-014 | Admin | Configure session timeout | Admin logged in | 1. Go to Settings tab 2. Set timeout to 30 min 3. Save | Timeout: 30 | Setting saved; users time out after 30 min | Medium | Major | Functional |
| TC-ADM-015 | Admin | System stats show correct counts | Users/policies exist | 1. View admin dashboard stats | — | User count, policy count, analysis count correct | High | Major | Functional |
| TC-ADM-016 | Admin | Non-admin blocked from `/admin` via URL | Regular user | 1. Navigate to `/admin` with regular token | — | Redirected or shown 403 | High | Critical | Security |

---

## 20. UI/UX Test Cases

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-UI-001 | Global | Dark mode active across all pages | None | 1. Enable dark mode 2. Navigate all pages | — | Dark theme applied everywhere; no light flash | Medium | Minor | UI |
| TC-UI-002 | Global | Dark mode persists on browser refresh | None | 1. Enable dark mode 2. Refresh | — | Dark mode still active | Medium | Minor | UI |
| TC-UI-003 | Global | Skeleton loaders shown before data loads | Throttled network | 1. Open any data page | — | Skeletons shown; no blank white flash | Medium | Minor | UI |
| TC-UI-004 | Global | Error toast shown on API failure | API unavailable | 1. Trigger any API call | — | Red/orange toast with descriptive error | High | Major | UI |
| TC-UI-005 | Global | Success toast shown on save | Any CRUD | 1. Save any form | — | Green success toast appears and auto-dismisses | Medium | Minor | UI |
| TC-UI-006 | Global | Sidebar navigation works for all items | Logged in | 1. Click every sidebar link | — | Each link navigates to correct page | High | Major | UI |
| TC-UI-007 | Global | Active route highlighted in sidebar | On /Dashboard | 1. View sidebar | — | Dashboard item highlighted; others not | Medium | Minor | UI |
| TC-UI-008 | Global | Logout clears token and redirects | Logged in | 1. Click Logout | — | Token cleared; redirected to `/login` | High | Critical | UI |
| TC-UI-009 | Global | Confirmation modals before destructive actions | — | 1. Delete any entity | — | Modal appears; requires explicit confirm | High | Major | UI |
| TC-UI-010 | Global | Keyboard navigation through interactive elements | None | 1. Tab through all UI | — | All buttons/inputs reachable via keyboard | Medium | Major | UI |
| TC-UI-011 | Global | Focus visible on focused elements | None | 1. Tab through UI | — | Focus ring visible (not suppressed) | Medium | Minor | UI |
| TC-UI-012 | Global | ARIA labels on icon-only buttons | None | 1. Inspect with axe or screen reader | — | Icon buttons have `aria-label` | Medium | Major | UI |
| TC-UI-013 | Responsive | Mobile 375px – no horizontal overflow | None | 1. Resize browser to 375px | — | All content fits; no scrollbar | High | Major | UI |
| TC-UI-014 | Responsive | Tablet 768px – grid adapts | None | 1. Resize to 768px | — | 2-column layout; no overlap | Medium | Minor | UI |
| TC-UI-015 | Responsive | Desktop 1440px – full layout | None | 1. View at 1440px | — | 4-column grid; proper spacing and alignment | High | Major | UI |

---

## 21. Cross-Browser & Responsive

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-CB-001 | Cross-Browser | Login renders correctly in Chrome | None | 1. Open `/login` in Chrome 125+ | — | Renders with no visual issues | High | Major | UI |
| TC-CB-002 | Cross-Browser | Login renders correctly in Firefox | None | 1. Open `/login` in Firefox 126+ | — | Renders correctly | High | Major | UI |
| TC-CB-003 | Cross-Browser | Login renders correctly in Edge | None | 1. Open `/login` in Edge | — | Renders correctly | High | Major | UI |
| TC-CB-004 | Cross-Browser | Dashboard charts in Safari | None | 1. Open `/Dashboard` in Safari 17+ | — | Recharts render without errors | Medium | Major | UI |
| TC-CB-005 | Cross-Browser | File upload in all browsers | None | 1. Upload PDF in Chrome, Firefox, Edge | `policy.pdf` | Upload succeeds in all | High | Critical | Functional |
| TC-CB-006 | Cross-Browser | PDF download in all browsers | Report generated | 1. Download in Chrome, Firefox, Edge | — | PDF downloads correctly | High | Major | Functional |
| TC-CB-007 | Responsive | Sidebar collapses on mobile | None | 1. Open on 375px device | — | Sidebar hidden; hamburger/toggle accessible | High | Major | UI |
| TC-CB-008 | Responsive | Tables scroll horizontally on mobile | None | 1. View GapsRisks table on 375px | — | Horizontal scroll; content not clipped | High | Major | UI |
| TC-CB-009 | Responsive | Signup form usable on mobile | None | 1. Complete signup on mobile viewport | — | All inputs accessible; no zoom forced | High | Major | UI |

---

## 22. Performance

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-PERF-001 | Global | Initial login page load time | None | 1. Load `/login` on fresh browser | — | Page interactive in < 3 seconds (LCP < 2.5s) | High | Major | Performance |
| TC-PERF-002 | Dashboard | Dashboard renders with 100+ policies | 100 policies | 1. Navigate to `/Dashboard` | — | Renders within 5 seconds; no UI freeze | High | Major | Performance |
| TC-PERF-003 | Policies | Large file (15MB) upload time | None | 1. Upload 15MB PDF | 15MB file | Uploads within 30 seconds; no timeout | Medium | Major | Performance |
| TC-PERF-004 | Reports | PDF generation time | Large analyzed policy | 1. Click Generate PDF | — | PDF generated within 10 seconds | Medium | Major | Performance |
| TC-PERF-005 | AIAssistant | Chat response time | None | 1. Send a question | — | Response received within 75 seconds (before timeout) | High | Major | Performance |
| TC-PERF-006 | Global | React Query cache prevents redundant fetches | Multiple page navigations | 1. Visit Dashboard 2. Navigate away 3. Return immediately | — | Second load uses cached data (near-instant) | Medium | Minor | Performance |
| TC-PERF-007 | Policies | Real-time polling does not degrade performance | Processing policy | 1. Leave Policies page open 5+ min | — | No memory leak; browser stays responsive | Medium | Major | Performance |

---

## 23. Security

| TC-ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|--------|--------------|---------------|------------|-----------|-----------------|----------|----------|------|
| TC-SEC-001 | Auth | Protected API requires JWT | Not logged in | 1. Call `GET /api/entities/Gap` without token | No Authorization header | `401 Unauthorized` returned | High | Critical | Security |
| TC-SEC-002 | Auth | Old token rejected after logout | User logged out | 1. Copy token 2. Logout 3. Use old token on API | Old JWT | `401 Unauthorized` | High | Critical | Security |
| TC-SEC-003 | Auth | Brute force protection | None | 1. Attempt login with wrong password 10+ times | Wrong passwords | Rate limiting or lockout triggered; `429 Too Many Requests` | High | Critical | Security |
| TC-SEC-004 | Auth | Password stored as bcrypt hash | DB access | 1. Register user 2. Inspect DB `users` table | — | `password_hash` column contains bcrypt hash, not plaintext | High | Critical | Security |
| TC-SEC-005 | Admin | Role escalation blocked for regular users | Regular user | 1. Call `PATCH /api/admin/users/{id}/role` with regular token | Regular JWT | `403 Forbidden` | High | Critical | Security |
| TC-SEC-006 | Admin | Admin-only endpoints enforce admin role | Regular user | 1. Call `GET /api/admin/users` with regular token | Regular JWT | `403 Forbidden` | High | Critical | Security |
| TC-SEC-007 | Upload | XSS via malicious filename | None | 1. Upload file named `<script>alert(1)</script>.pdf` | Malicious filename | Filename sanitized; no script executes | High | Critical | Security |
| TC-SEC-008 | Upload | Reject executable file extensions | None | 1. Upload `.php`, `.sh`, `.exe` file | `shell.php` | Upload rejected with error | High | Critical | Security |
| TC-SEC-009 | API | SQL injection in search/filter inputs | None | 1. Enter `' OR 1=1 --` in gap search | Injection payload | Input sanitized; no DB error; no data leak | High | Critical | Security |
| TC-SEC-010 | Auth | No user enumeration in forgot-password | None | 1. Request reset for unregistered email | `ghost@test.com` | Same generic "if account exists, OTP sent" message | High | Major | Security |
| TC-SEC-011 | Auth | HTTPS enforced in production | Production env | 1. Access via `http://` URL | — | Redirected to `https://` | High | Major | Security |
| TC-SEC-012 | Auth | JWT contains no sensitive data | User logged in | 1. Decode JWT from localStorage | — | No plaintext password; minimal claims only | High | Major | Security |
| TC-SEC-013 | OTP | OTP cannot be reused | OTP verified | 1. Use OTP 2. Try same OTP again | Same OTP | Rejected: "OTP already used or expired" | High | Critical | Security |

---

## 24. API Test Cases

| TC-ID | Endpoint | Test Scenario | Preconditions | Request | Test Data | Expected Response | Priority | Severity | Type |
|-------|----------|--------------|---------------|---------|-----------|-------------------|----------|----------|------|
| TC-API-001 | `POST /api/auth/register` | Successful registration | Email not in DB | POST with valid JSON | `{first_name, last_name, phone, email, password}` | `201` / `200`; user created; OTP sent | High | Critical | API |
| TC-API-002 | `POST /api/auth/register` | Duplicate email | Email exists | POST with existing email | `{email: existing@test.com}` | `400` / `409`; error message | High | Major | API |
| TC-API-003 | `POST /api/auth/login` | Valid credentials | User registered | POST `{email, password}` | Valid creds | `200`; `{access_token, token_type}` | High | Critical | API |
| TC-API-004 | `POST /api/auth/login` | Wrong password | User registered | POST with wrong password | Wrong password | `401 Unauthorized` | High | Critical | API |
| TC-API-005 | `GET /api/auth/me` | Get current user | Authenticated | GET with Bearer token | Valid JWT | `200`; `{id, email, first_name, role}` | High | Major | API |
| TC-API-006 | `POST /api/integrations/upload` | Upload valid PDF | Authenticated | Multipart POST with PDF + framework | `policy.pdf`, framework: ISO 27001 | `200`; `{policy_id, status: "uploaded"}` | High | Critical | API |
| TC-API-007 | `POST /api/integrations/upload` | Upload without auth | Not authenticated | No Authorization header | `policy.pdf` | `401 Unauthorized` | High | Critical | API |
| TC-API-008 | `POST /api/functions/analyze_policy` | Trigger analysis | Policy uploaded | POST `{policy_id}` | Valid policy_id | `200`; analysis started | High | Critical | API |
| TC-API-009 | `GET /api/entities/Gap` | Fetch user's gaps | Authenticated | GET with token | — | `200`; JSON array of gaps | High | Major | API |
| TC-API-010 | `PUT /api/entities/Gap/{id}` | Update gap owner | Gap exists | PUT `{owner_name, status}` | Valid gap_id | `200`; updated gap object | High | Major | API |
| TC-API-011 | `GET /api/dashboard/stats` | Get dashboard stats | Authenticated | GET with token | — | `200`; `{total_policies, score, gaps, analyses}` | High | Major | API |
| TC-API-012 | `POST /api/functions/generate_report` | Generate PDF report | Policy analyzed | POST `{policy_id, format: "pdf"}` | Valid policy_id | `200`; report URL returned | High | Major | API |
| TC-API-013 | `POST /api/functions/chat_assistant` | Send chat message | Authenticated | POST `{message}` | `"What are my gaps?"` | `200`; `{response: "..."}` | High | Critical | API |
| TC-API-014 | `GET /api/admin/users` | Admin fetches all users | Admin token | GET with admin JWT | Admin JWT | `200`; user list | High | Critical | API |
| TC-API-015 | `GET /api/admin/users` | Regular user blocked | Regular token | GET with regular JWT | Regular JWT | `403 Forbidden` | High | Critical | API |
| TC-API-016 | `POST /api/mappings/{id}/accept` | Accept a mapping | Mapping exists | POST with token | Valid mapping_id | `200`; mapping updated to accepted | High | Major | API |
| TC-API-017 | `POST /api/auth/change-password` | Change password | Authenticated | POST `{current_password, new_password}` | Valid + new passwords | `200`; success | High | Major | API |
| TC-API-018 | `DELETE /api/entities/Policy/{id}` | Delete policy | Policy exists | DELETE with token | Valid policy_id | `200` / `204`; policy removed | High | Major | API |

---

## 25. End-to-End User Journeys

| TC-ID | Journey | Steps | Test Data | Expected Result | Priority | Severity | Type |
|-------|---------|-------|-----------|-----------------|----------|----------|------|
| TC-E2E-001 | **New user onboarding** | 1. Visit `/` → click Sign Up 2. Register 3. Verify OTP 4. Login 5. Upload policy 6. Wait for analysis 7. View results in Analyses | New email, valid PDF | Full journey completes; compliance results visible | High | Critical | E2E |
| TC-E2E-002 | **Compliance analysis → report export** | 1. Login 2. Upload policy 3. Wait for analysis 4. Review mappings (accept/reject) 5. View gaps 6. Generate PDF report 7. Download | Analyzed policy | PDF downloaded with correct score, gaps, and control mappings | High | Critical | E2E |
| TC-E2E-003 | **Gap lifecycle management** | 1. Login 2. Open GapsRisks 3. Filter by Critical 4. Assign owner to 3 gaps 5. Change status to In Progress 6. Mark as Resolved 7. Confirm filtered view updated | Gaps exist | Full gap lifecycle tracked; filters reflect state changes | High | Major | E2E |
| TC-E2E-004 | **AI-assisted compliance review** | 1. Login 2. Open AIAssistant 3. Ask about top gaps 4. Navigate to AIInsights 5. Generate insights 6. Open Simulation 7. Select controls 8. View score improvement | Analyzed policy | AI provides contextual guidance; simulation shows improvement delta | High | Major | E2E |
| TC-E2E-005 | **Admin user management + framework** | 1. Login as admin 2. Navigate to `/admin` 3. Add new framework 4. Create/enable a user 5. View activity logs | Admin creds | Framework added; user enabled; all actions in audit log | High | Critical | E2E |
| TC-E2E-006 | **Password reset full flow** | 1. Go to `/login` 2. Click Forgot Password 3. Enter email 4. Enter OTP from email 5. Set new password 6. Login with new password 7. Verify data intact | Registered email | Password reset; login succeeds; user's policies/data intact | High | Critical | E2E |
| TC-E2E-007 | **Multi-framework analysis comparison** | 1. Upload same policy with ISO 27001 2. Upload same policy with NCA ECC 3. View Dashboard 4. Compare scores | Same PDF × 2 frameworks | Two separate results; different scores per framework in Dashboard | High | Major | E2E |

---

## 26. Regression

| TC-ID | Scenario | Trigger | Test Steps | Expected Result | Priority | Severity | Type |
|-------|---------|---------|------------|-----------------|----------|----------|------|
| TC-REG-001 | Login still works after profile update | After user updates name/email | 1. Update profile 2. Logout 3. Login with original credentials | Login succeeds; updated name shown | High | Critical | Regression |
| TC-REG-002 | Old policies unaffected by new upload | After new policy uploaded | 1. Note existing policies 2. Upload new policy | Old policies unchanged; new appears in addition | High | Major | Regression |
| TC-REG-003 | Dashboard stats increment after new analysis | New policy analyzed | 1. Note stats 2. Analyze new policy 3. Check stats | Counts increment by 1 | High | Major | Regression |
| TC-REG-004 | Existing gaps unaffected by re-analysis | Re-analysis triggered | 1. Note existing gaps 2. Reanalyze policy | Existing gaps unchanged; new gaps appear separately | High | Major | Regression |
| TC-REG-005 | Other users unaffected by admin changes | Admin disables one user | 1. Admin disables user A 2. User B logs in | User B unaffected; login succeeds | High | Critical | Regression |
| TC-REG-006 | Mapping decisions persist after new upload | Decisions made; new policy uploaded | 1. Accept mappings 2. Upload new policy 3. Return to MappingReview | Original decisions still shown for original policy | High | Major | Regression |

---

## 27. Automation Recommendations

### Recommended Tool Stack

| Tool | Use Case | Why |
|------|----------|-----|
| **Playwright** | E2E, cross-browser, file upload/download | Best fit for React SPA + async FastAPI; native multi-browser; handles file pickers and downloads natively |
| **Cypress** | Component & UI interaction tests | Fast feedback loop for React UI; excellent DX for frontend-only flows |
| **Pytest + httpx** | Backend API test suite | Matches FastAPI's async architecture; built-in fixture support |
| **Axe-core + Playwright** | Automated accessibility audits | Inject axe into pages and capture WCAG violations per page |
| **k6** | API performance / load tests | Simulates concurrent users against FastAPI; threshold-based pass/fail |

---

### Automation Priority Order

**Phase 1 – Automate First (Highest ROI)**

| # | TC-IDs | Rationale |
|---|--------|-----------|
| 1 | TC-AUTH-001–010 | Auth runs every release; regression-critical |
| 2 | TC-API-001–018 | Full API coverage with Pytest; fast and stable |
| 3 | TC-E2E-001, TC-E2E-002 | Core user journeys must never silently break |
| 4 | TC-POL-001–008 | Upload + analysis is the platform's core value |
| 5 | TC-SEC-001–006 | Auth security is non-negotiable |

**Phase 2 – Automate Next**

| # | TC-IDs | Rationale |
|---|--------|-----------|
| 6 | TC-DASH-001–006 | First touchpoint after login |
| 7 | TC-GAP-001–009 | Core workflow; data-driven and automatable |
| 8 | TC-REP-001–005 | PDF/CSV output is a key deliverable |
| 9 | TC-ADM-001–016 | Admin flows; automate RBAC checks especially |
| 10 | TC-REG-001–006 | Regression suite for CI/CD gate |
| 11 | TC-CB-001–009 | Cross-browser via Playwright multi-project config |

**Phase 3 – Keep Manual**

| TC-IDs | Reason |
|--------|--------|
| TC-CHAT-001–009 | AI response quality hard to assert deterministically |
| TC-SIM-001–004 | Simulation scores vary by data set |
| TC-PERF-003, TC-PERF-005 | Require calibrated load environment |
| TC-UI-012, TC-UI-010 | Accessibility and keyboard flows need human judgment for edge cases |
| TC-INS-001–005 | AI-generated insights; output varies |

---

### Sample Playwright Test Skeleton (E2E-001)

```typescript
// tests/e2e/onboarding.spec.ts
import { test, expect } from '@playwright/test';

test('New user onboarding – TC-E2E-001', async ({ page }) => {
  await page.goto('/signup');
  await page.fill('[name="firstName"]', 'Jana');
  await page.fill('[name="lastName"]', 'Test');
  await page.fill('[name="phone"]', '0512345678');
  await page.fill('[name="email"]', `jana+${Date.now()}@test.sa`);
  await page.fill('[name="password"]', 'Test@1234');
  await page.click('[type="submit"]');
  await expect(page).toHaveURL(/verify-otp/);
  // OTP step: inject OTP from email via API or test helper
});
```

### Sample Pytest API Skeleton

```python
# tests/api/test_auth.py
import httpx, pytest

BASE = "http://localhost:8000"

def test_login_valid():
    r = httpx.post(f"{BASE}/api/auth/login", json={
        "email": "user@hemaya.sa", "password": "Test@1234"
    })
    assert r.status_code == 200
    assert "access_token" in r.json()

def test_login_wrong_password():
    r = httpx.post(f"{BASE}/api/auth/login", json={
        "email": "user@hemaya.sa", "password": "wrong"
    })
    assert r.status_code == 401
```

---

*Generated by Senior QA Engineer analysis of Hemaya codebase — 2026-05-08*  
*Total: 162 test cases across 26 modules*
