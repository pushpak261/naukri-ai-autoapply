# Advanced Scam Detector (v3: The Weighted Scoring System)

You make an incredibly valid point. Genuine startups and HRs *do* sometimes use Gmail, put phone numbers in descriptions, and host legitimate Walk-in drives. Our current "Instant Reject" algorithm is too aggressive and will cause false positives (blocking genuine jobs).

To solve this, I will upgrade the algorithm from a "black-and-white" system to an **Intelligent Weighted Scoring System**.

## The Problem with V2
In V2, if a job title contained "Walk-in", it was instantly destroyed. 

## The Solution: V3 Weighted Scoring
In V3, jobs start with 0 points. Different red flags add different penalty scores. If a job crosses the `SCAM_THRESHOLD` (e.g., 100 points), it is classified as a scam and rejected. This allows "grey area" traits to exist, as long as they don't pile up!

### Proposed Scoring System (Threshold = 100 to Reject)

**Level 1: Absolute Scams (Instant Reject - 100 pts)**
No genuine company will ever ask for these.
- Description contains: "Registration fee", "Security deposit", "Pay before joining", "Laptop charges"

**Level 2: High Suspicion (80 pts)**
Almost always spam/BPO, but requires one more minor red flag to trigger rejection.
- Title/Company contains: "BPO", "International Voice", "Night shift", "Data entry"
- Company name contains: "Placement", "Manpower", "Staffing"

**Level 3: Medium Suspicion (50 pts)**
Commonly used by scammers, but sometimes used by genuine startups.
- Title contains: "Walk-in", "Urgent Hiring", "Direct Joining"
- Title/Company contains: 10-digit Phone Number, "@gmail.com" or "@yahoo.com"

**Level 4: Low Suspicion (30 pts)**
Very minor flags that only trigger rejection if piled up with other issues.
- Company name ends in "HR"

**The Whitelist Shield (-500 pts)**
- Known massive companies (TCS, Infosys, etc.) get a massive negative score, making them immune to the threshold.

### Example Scenarios
- **Scenario A (Genuine Walk-in):** Title is "Walk-in for Java Developer" at "Tech Mahindra" (Genuine). Score: 50 (Walk-in) - 500 (Whitelist) = **-450 points**. **(SAFE)**
- **Scenario B (Genuine Startup):** Title is "Python Developer" at "Nexus Tech". Description has a contact number. Score: 50 (Phone number). **(SAFE)**
- **Scenario C (Fake Job):** Title is "Walk-in Urgent Hiring" at "Creative Hands HR" with a @gmail.com email. Score: 50 (Walk-in) + 50 (Urgent) + 30 (HR name) + 50 (Gmail) = **180 points**. **(REJECTED)**

### [MODIFY] [specifications.py](file:///c:/Users/pushp/Music/AI_Agent_Naukri_refactored/refactored/src/naukri_agent/core/domain/specifications.py)
- Refactor `ConsultancyScamSpecification` to calculate a cumulative `scam_score` instead of returning boolean instant-rejects.
- Update tests in `test_scam_detector.py` to assert the new scoring threshold logic.

## Open Questions
- Do the proposed penalty scores look well-balanced to you? 

If you are happy with this logic, click **Proceed** and I will build the ultimate scoring engine!
