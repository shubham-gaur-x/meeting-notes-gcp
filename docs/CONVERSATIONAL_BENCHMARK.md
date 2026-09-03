# 📊 Conversational & Vague Query Evaluation Benchmark

This document benchmarks how the system handles vague, conversational, second-person queries without using third-person names ('Michael Baylard') and providing direct actionable links.

## Summary Scorecard

| # | Scenario | Query | Latency | 2nd-Person ('You/Your') | Zero Real-Name Leak | Action Links | Quality Score |
| :- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | Open-Ended Task Ingestion | *"what do i need to do?"* | 7.19s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **2** | Missing / Unresolved Items | *"what am i missing or forgetting?"* | 5.29s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **3** | Urgent Priorities | *"anything urgent on my plate?"* | 6.55s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **4** | Vague Stakeholder Reference | *"what was that presentation thing Katrisa asked about?"* | 4.27s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **5** | Informal System Inquiries | *"did someone email me about my hours or timecards?"* | 17.23s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **6** | Submissions & Forms | *"what do i have to fill out or submit?"* | 5.49s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **7** | Pending Stakeholders | *"who is waiting on something from me?"* | 4.89s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **8** | Executive Action Plan | *"summarize what i should focus on next"* | 8.46s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **9** | Event / Logistics | *"what's going on with orientation?"* | 3.92s | ✅ Yes | ✅ Passed (Clean) | ✅ Yes | **10/10 (A+)** |
| **10** | Negative / Unrelated Check | *"did anyone mention bonuses or salary reviews?"* | 3.68s | ✅ Yes | ✅ Passed (Clean) | — | **10/10 (A+)** |

---

## Detailed Conversational Responses

### Scenario 1: Open-Ended Task Ingestion
**User Prompt**: *"what do i need to do?"*  
**Latency**: `7.19s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a prioritized briefing of your pending action items and required tasks:

### ⚡ High Priority & Compliance Actions
* **Submit & Fix Salesforce Timecards:** Review and address any timecard(s) currently in 'Saved' or 'Rejected' status within the Salesforce Services Delivery Workspace.
  * [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

* **Update PSA Skills & Certifications (Due: Aug 26, 2026):** Add and submit your updated technical skills and certification details in PSA for RMG/L&D compliance, then notify your L1 manager for review.
  * [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

* **Complete Professional Services Profile Slide:** Update your assigned slide in the *Onshore: Professional Services Profiles* presentation with your technical skill set and a professional photo for Google Flex program staffing.
  * [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

* **Verify Identity for Empower HSA (Due: Oct 21, 2026):** Upload copies of your Social Security card and unexpired government-issued photo ID (plus proof of address if applicable) to Optum Bank to finalize your HSA enrollment.
  * [📄 Open Optum HSA Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

---

### 📋 Optional Follow-Ups
* **Gemini Enterprise Training Survey:** Complete the follow-up survey if you are interested in future client implementations, upcoming trainings, or joining the dedicated Google Chat space.
  * [📝 Open Follow-Up Form](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

---

### Scenario 2: Missing / Unresolved Items
**User Prompt**: *"what am i missing or forgetting?"*  
**Latency**: `5.29s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a breakdown of your pending action items and tasks that require attention.

### 🚨 Immediate & Operational Tasks
- **Review Salesforce Timecards**: Inspect and submit any timecards currently marked as 'Saved' or 'Rejected' in the Services Delivery Workspace.
  - [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)
- **Update Professional Services Profile**: Add your technical skillset and a professional photo to the slide deck for Google's Flex program staffing.
  - [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)
- **Update Skills in PSA (Due: Aug 26, 2026)**: Update your skills and certification details in PSA for RMG/L&D compliance and notify your L1 manager.
  - [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

### 📄 Benefits & Compliance
- **HSA Identity Verification (Due: Oct 21, 2026)**: Upload copies of your Social Security card and unexpired government photo ID to Optum Bank to finalize your Empower HSA enrollment.
  - [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

### 📝 Surveys & Follow-Ups
- **Gemini Enterprise Training Follow-Up**: Complete the feedback and interest survey if you want to participate in future client implementations, training sessions, or join the dedicated Google Chat space.
  - [📝 Open Survey Form](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

---

### Scenario 3: Urgent Priorities
**User Prompt**: *"anything urgent on my plate?"*  
**Latency**: `6.55s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a breakdown of the most urgent and time-sensitive items currently on your plate.

### **Immediate Operational & Compliance Tasks**
* **Review & Submit Salesforce Timecards**
  * **Details:** You have timecards in "Saved" or "Rejected" status in Salesforce requiring immediate review in the Services Delivery Workspace to ensure payroll and billing compliance.
  * **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

* **Update Skill & Certification Details in PSA**
  * **Due Date:** August 26, 2026 (EOD)
  * **Details:** Delivery Excellence requires all technical associates to update skill and certification details in PSA for RMG allocations and notify your L1 manager for review.
  * **Links:** [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

### **Profile & Staffing Action Items**
* **Update Professional Services Profile Slide**
  * **Details:** Update your technical profile skill set and upload a professional photo in the presentation deck to support staffing for Google's Flex program.
  * **Links:** [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

### **Upcoming Deadlines & Administrative Items**
* **Empower HSA Identity Verification**
  * **Due Date:** October 21, 2026
  * **Details:** Submit copies of your Social Security card and unexpired government photo ID to Optum Bank to finalize your HSA enrollment and prevent account cancellation.
  * **Links:** [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

* **Gemini Enterprise Training Follow-Up Survey**
  * **Details:** Complete the survey if you are interested in upcoming client implementations, future training sessions, or joining the dedicated Google Chat space.
  * **Links:** [📝 Open Follow-Up Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

---

### Scenario 4: Vague Stakeholder Reference
**User Prompt**: *"what was that presentation thing Katrisa asked about?"*  
**Latency**: `4.27s` | **Nodes Accessed**: `17`  

**Assistant Response**:
Katrisa Brock requested that you update your slide in the **Onshore: Professional Services Profiles** presentation to support staffing for Google's Flex program.

### Task Details
* **Action Required:** Update your slide with your technical profile skill set and a professional photo.
* **Purpose:** Support resource allocation and staffing for Google's Flex program.
* **Relevant Links:**
  * [📊 Open Google Slides Presentation](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false)
  * [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26)
  * [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

---

### Scenario 5: Informal System Inquiries
**User Prompt**: *"did someone email me about my hours or timecards?"*  
**Latency**: `17.23s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Yes, BizOps sent you an email regarding timecards in **'Saved'** or **'Rejected'** status in Salesforce that require your immediate review.

### **Timecard Action Required**
- **Details**: You need to review and submit your pending timecard(s) via the Salesforce Services Delivery Workspace.
- **Related Links**: [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007) | [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27)

---

### Scenario 6: Submissions & Forms
**User Prompt**: *"what do i have to fill out or submit?"*  
**Latency**: `5.49s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a breakdown of everything you currently need to fill out, update, or submit across your active tasks:

### **1. Identity Verification for HSA Enrollment**
* **Action:** Upload or submit copies of your Social Security card and an unexpired government-issued photo ID (plus proof of address if required) to Optum Bank to finalize your Empower HSA enrollment and prevent account cancellation.
* **Due Date:** October 21, 2026
* **Links:** [📄 Open Optum HSA Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

### **2. Salesforce Timecard Submission**
* **Action:** Review and submit your timecard(s) currently sitting in **'Saved'** or **'Rejected'** status in the Salesforce Services Delivery Workspace.
* **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

### **3. Professional Services Profile Slide**
* **Action:** Update your technical skill set profile and add your professional photo in the team slide deck for Google Flex staffing.
* **Links:** [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

### **4. PSA Skill & Certification Details**
* **Action:** Enter your technical skill and certification details in PSA for RMG and L&D compliance, then notify your L1 manager for review.
* **Due Date:** August 26, 2026 EOD
* **Links:** [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

### **5. Gemini Enterprise Training Survey (Optional)**
* **Action:** Complete the follow-up survey if you are interested in customer implementations, upcoming training sessions, or joining the dedicated Google Chat space.
* **Links:** [📝 Open Google Forms Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

---

### Scenario 7: Pending Stakeholders
**User Prompt**: *"who is waiting on something from me?"*  
**Latency**: `4.89s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a breakdown of the individuals and teams currently waiting on deliverables or administrative submissions from you:

* **Katrisa Brock (Google Flex Staffing)**
  * **Task:** Update your slide in the Professional Services profile deck with your technical skillset and a professional photo.
  * **Links:** [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

* **BizOps**
  * **Task:** Review and resubmit timecards currently sitting in "Saved" or "Rejected" status in the Salesforce Services Delivery Workspace.
  * **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

* **Optum Bank**
  * **Task:** Submit copies of your Social Security card and an unexpired government photo ID (due October 21, 2026) to complete your Empower HSA identity verification.
  * **Links:** [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

* **Delivery Excellence, RMG & L1 Management**
  * **Task:** Add your skill and certification details into PSA and notify your L1 manager for review and compliance approval (due August 26, 2026).
  * **Links:** [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

* **Mallory Webber**
  * **Task:** Complete the follow-up survey regarding future client implementations, training sessions, and the Google Chat space if you are interested in participating.
  * **Links:** [📝 Open Follow-Up Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

---

### Scenario 8: Executive Action Plan
**User Prompt**: *"summarize what i should focus on next"*  
**Latency**: `8.46s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is a prioritized summary of your key action items and upcoming tasks to focus on next:

### 🚨 Immediate Operational & Compliance Tasks
* **Review Saved/Rejected Salesforce Timecards**: Inspect and resolve timecard entries currently in "Saved" or "Rejected" status within the Services Delivery Workspace.
  * [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)
* **Update Skill & Certification Details in PSA**: Complete your technical profile and certification updates in PSA and notify your L1 manager for compliance and RMG allocations (**Due: August 26, 2026**).
  * [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

### 👤 Staffing & Profile Updates
* **Update Professional Services Profile Slide**: Add your technical skillset details and a professional photo to the Onshore Profiles deck to support staffing for Google's Flex program.
  * [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

### 📄 Benefits & Follow-ups
* **Submit Optum Bank HSA Identity Verification**: Provide copies of your Social Security card and unexpired government photo ID to finalize your Empower HSA enrollment (**Due: October 21, 2026**).
  * [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)
* **Complete Gemini Enterprise Training Survey**: Submit the follow-up survey if you are interested in upcoming client implementations, future trainings, or the dedicated chat space.
  * [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [📝 Open Follow-Up Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor)

---

### Scenario 9: Event / Logistics
**User Prompt**: *"what's going on with orientation?"*  
**Latency**: `3.92s` | **Nodes Accessed**: `16`  

**Assistant Response**:
Here is the latest update regarding your **Monthly Orientation Session** held on August 19, 2026.

### **Overview & Details**
* **Purpose**: Hosted by Pawankumar Bhagat to introduce new hires to various company support functions and team structures.
* **Venue Update**: The in-person meeting was relocated to the **Nalanda cabin on the 3rd floor** of the Pune office.

### **Action Items & Links**
* **Session Attendance**: Reach the venue by 2:20 PM or join remotely.
  * [📹 Join Google Meet](https://meet.google.com/xhs-wiuc-bzp)
  * [🔷 View Jira MDP-29](https://michael-baylard.atlassian.net/browse/MDP-29)
  * [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00ee4e00665f1f)

---

### Scenario 10: Negative / Unrelated Check
**User Prompt**: *"did anyone mention bonuses or salary reviews?"*  
**Latency**: `3.68s` | **Nodes Accessed**: `16`  

**Assistant Response**:
I reviewed your meeting history and task records, and found no mention of bonuses or salary reviews.

---
