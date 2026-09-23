# 📊 Ask Chatbot Evaluation & Quality Benchmark

This document benchmarks natural language retrieval, synthesis quality, human readability, link grounding, and latency across 10 executive scenarios.

## Summary Scorecard

| # | Scenario | Query | Latency | Nodes | Links Included | Score |
| :- | :--- | :--- | :---: | :---: | :---: | :---: |
| **1** | Direct Assignments | *"What tasks or action items are assigned directly to Michael Baylard?"* | 5.60s | 17 | Yes | **10/10 (A+)** |
| **2** | Stakeholder Instructions | *"What did Katrisa Brock assign me to do, and where is the document link?"* | 5.02s | 17 | Yes | **10/10 (A+)** |
| **3** | Deadlines & Dates | *"What deadlines do I have coming up this week or in August 2026?"* | 7.22s | 16 | Yes | **10/10 (A+)** |
| **4** | Decisions & Logistics | *"Where is the new hire orientation session taking place, and what was decided about the venue?"* | 3.53s | 16 | Yes | **10/10 (A+)** |
| **5** | Multi-Hop Ownership | *"How does the PSA skill and certification update process work, and who approves what?"* | 6.65s | 16 | Yes | **10/10 (A+)** |
| **6** | System Tasks | *"What do I need to do regarding my Salesforce timecards, and where do I check them?"* | 5.02s | 16 | Yes | **10/10 (A+)** |
| **7** | Training Follow-Ups | *"What follow-up actions came out of the Gemini Enterprise training session?"* | 4.71s | 16 | Yes | **10/10 (A+)** |
| **8** | Document Requirements | *"What documents do I need to submit for Optum Bank and what is the deadline?"* | 4.81s | 16 | Yes | **10/10 (A+)** |
| **9** | Urgent Priorities | *"What are the highest priority items that need attention right now?"* | 6.25s | 16 | Yes | **10/10 (A+)** |
| **10** | Negative Grounding Check | *"What was the budget approved for the Q4 Kubernetes multi-cloud migration?"* | 7.17s | 16 | None needed | **10/10 (A+)** |

---

## Detailed Responses & Analysis

### Scenario 1: Direct Assignments
**Query**: *"What tasks or action items are assigned directly to Michael Baylard?"*  
**Latency**: `5.60s` | **Context Nodes**: `17`  

**Output**:
You (Michael Baylard) currently have 3 action items assigned directly to you across your workspace:

* **Submit Identity Verification for Empower HSA Enrollment**
  * **Description:** Upload or send copies of your Social Security card and unexpired government-issued photo ID (along with proof of address if needed) to Optum Bank to finalize your HSA enrollment.
  * **Due Date:** October 21, 2026
  * **Links:** [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

* **Update Professional Services Profile Slide**
  * **Description:** Update your assigned slide with your technical profile skill set and a professional photo to support staffing for Google's Flex program.
  * **Source:** *Onshore: Professional Services Profiles* (assigned by Katrisa Brock)
  * **Links:** [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

* **Review Saved or Rejected Timecards in Salesforce**
  * **Description:** Check and address any timecards currently in "Saved" or "Rejected" status within the Salesforce Services Delivery Workspace.
  * **Source:** *[Action Required] Submit YOUR Timecard in Salesforce*
  * **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

---

### Scenario 2: Stakeholder Instructions
**Query**: *"What did Katrisa Brock assign me to do, and where is the document link?"*  
**Latency**: `5.02s` | **Context Nodes**: `17`  

**Output**:
Katrisa Brock assigned you to update your technical profile skill set and add a professional photo in the team slide deck to support staffing for Google's Flex program.

### Task Details
* **Assignment:** Update slide with technical profile skill set and professional photo
* **Assigned By:** Katrisa Brock
* **Owner:** You (Michael Baylard)
* **Context:** Support staffing allocations for Google's Flex program
* **Relevant Links:**
  * [📊 Open Professional Services Profiles Slide Deck](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false)
  * [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26)
  * [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

---

### Scenario 3: Deadlines & Dates
**Query**: *"What deadlines do I have coming up this week or in August 2026?"*  
**Latency**: `7.22s` | **Context Nodes**: `16`  

**Output**:
Here are the upcoming and scheduled deadlines and key action items for August 2026 across your tasks and meetings:

### **August 2026 Deadlines & Active Items**

* **Update Skill and Certification Details in PSA**
  * **Due Date:** August 26, 2026 (EOD)
  * **Owner:** Pending Technical Associates
  * **Details:** Update your skills and certification details in PSA for RMG and L&D compliance, then notify your L1 manager for review.
  * **Links:** [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

* **Review Saved or Rejected Timecard(s) in Salesforce**
  * **Due Date:** Immediate / As soon as possible (Notified August 24, 2026)
  * **Owner:** You (Michael Baylard)
  * **Details:** Inspect and resubmit any timecards in 'Saved' or 'Rejected' status via the Salesforce Services Delivery Workspace.
  * **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

* **Update Technical Profile Skill Set & Photo in Google Slides**
  * **Due Date:** Immediate (Requested August 18, 2026)
  * **Owner:** You (Michael Baylard)
  * **Details:** Update your profile slide with your technical skills and a professional photo to support staffing for Google's Flex program.
  * **Links:** [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

* **Attend Monthly Orientation Session**
  * **Due Date:** August 19, 2026 at 2:20 PM
  * **Owner:** All Attendees
  * **Details:** Join in-person at the Nalanda cabin (3rd floor) or connect online.
  * **Links:** [📹 Join Google Meet](https://meet.google.com/xhs-wiuc-bzp) | [🔷 View Jira MDP-29](https://michael-baylard.atlassian.net/browse/MDP-29) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00ee4e00665f1f)

---

### **Upcoming Later Deadline**
* **Optum Bank HSA Identity Verification**
  * **Due Date:** October 21, 2026
  * **Owner:** You (Michael Baylard)
  * **Details:** Submit Social Security card and unexpired government-issued photo ID to complete HSA enrollment.
  * **Links:** [📄 Open Optum Verification Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

---

### Scenario 4: Decisions & Logistics
**Query**: *"Where is the new hire orientation session taking place, and what was decided about the venue?"*  
**Latency**: `3.53s` | **Context Nodes**: `16`  

**Output**:
The new hire orientation session was relocated to the **Nalanda cabin on the 3rd floor of the Pune office**, with a virtual option available via Google Meet.

### Venue Details & Decisions
* **Location Decision:** It was officially decided to relocate the in-person session to the **Nalanda cabin (3rd Floor, Pune office)**.
* **Virtual Access:** Attendees joining remotely can connect via [📹 Join Google Meet](https://meet.google.com/xhs-wiuc-bzp) (or dial in at [📞 Phone Access](https://tel.meet/xhs-wiuc-bzp?pin=8478360460241)).
* **Related Action Item:** Attendees were asked to reach the venue by 2:20 PM or join virtually via [🔷 View Jira MDP-29](https://michael-baylard.atlassian.net/browse/MDP-29) / [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00ee4e00665f1f).

---

### Scenario 5: Multi-Hop Ownership
**Query**: *"How does the PSA skill and certification update process work, and who approves what?"*  
**Latency**: `6.65s` | **Context Nodes**: `16`  

**Output**:
The PSA skill and certification update process requires technical associates to log their profile details in PSA for RMG and L&D compliance, followed by a split approval workflow between direct managers and the Learning & Development team.

### **Process Workflow**
1. **Submission by Associates**
   - **Action**: All technical associates must update their skill set and certification details directly within PSA and notify their direct manager for review.
   - **Compliance Deadline**: Due by August 26, 2026 EOD.
   - **Support**: If any technical issues arise during submission, associates should raise a Jira ticket.
   - **Reference Task**: [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

2. **Approval Responsibilities**
   - **L1 Managers**: Responsible for reviewing and approving all **submitted skills** in PSA ([🔷 View Jira MDP-31](https://michael-baylard.atlassian.net/browse/MDP-31)).
   - **L&D Team**: Responsible for reviewing and approving all **submitted certifications** ([🔷 View Jira MDP-32](https://michael-baylard.atlassian.net/browse/MDP-32)).

---

### Scenario 6: System Tasks
**Query**: *"What do I need to do regarding my Salesforce timecards, and where do I check them?"*  
**Latency**: `5.02s` | **Context Nodes**: `16`  

**Output**:
BizOps has requested that you review and submit your pending timecards in Salesforce.

### What You Need to Do
* **Review Pending Timecards:** Inspect any timecards currently marked in **'Saved'** or **'Rejected'** status and submit them for approval.
* **Where to Check:** Go to the **Services Delivery Workspace** in Salesforce to access your timecards.
* **Support Resources:** Training and support materials are available via `go/coe` or Jira if you encounter issues.

### Associated Task
* **Review Timecards in Salesforce**  
  **Owner:** You (Michael Baylard)  
  **Reference:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) · [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

---

### Scenario 7: Training Follow-Ups
**Query**: *"What follow-up actions came out of the Gemini Enterprise training session?"*  
**Latency**: `4.71s` | **Context Nodes**: `16`  

**Output**:
Following the **Gemini Enterprise Training: AI Adoption for Clients!** session, attendees were requested to complete a follow-up survey to indicate interest in future initiatives.

### **Action Items & Follow-Ups**
* **Complete Follow-Up Survey**
  * **Owner:** Attendees
  * **Details:** Complete the survey if you are interested in future customer implementations, upcoming training sessions, and being added to the dedicated Google Chat space.
  * **Links:** [📝 Complete Follow-Up Survey](https://docs.google.com/forms/d/e/1FAIpQLSfMHarusS9VcySlQ2RmhAyvKF_ui4OmXy49fpFRKdHkk5JSxA/viewform?usp=publish-editor) | [🔷 View Jira MDP-28](https://michael-baylard.atlassian.net/browse/MDP-28) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a011bbf7f0d026e)

### **Session Resources**
* [📄 View Meeting Notes](https://docs.google.com/document/d/1ugdMxE9UFww-e416Qc6M2VNyPX-eQzrSSYgK9TRwT80/edit?tab=t.o3ihl8ci83ww)
* [🎥 Watch Session Recording](https://drive.google.com/file/d/1jhl9KHEErPl2RxCf4BuUL-nxgSkDmEj5/view?usp=sharing)
* [📄 Access Training Handout](https://docs.google.com/document/d/1iKqW1-VWqB1XSgrQ9OW_UtQJyOD4CPj2NBxUPEO7Ruc/edit?usp=sharing)

---

### Scenario 8: Document Requirements
**Query**: *"What documents do I need to submit for Optum Bank and what is the deadline?"*  
**Latency**: `4.81s` | **Context Nodes**: `16`  

**Output**:
To finalize your Empower HSA enrollment, you need to submit copies of your identity verification documents by **October 21, 2026**.

### Required Documents
* **Social Security Card**: A clear copy of your card.
* **Photo ID**: A valid, unexpired government-issued photo ID.
* **Proof of Address**: Supplemental documentation if required to verify your address.

### Action & Resources
* **Task**: Upload or send identity verification documents to Optum Bank.
* **Owner**: You (Michael Baylard)
* **Deadline**: October 21, 2026
* **Action Links**: [📄 Open Optum HSA Enrollment Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

---

### Scenario 9: Urgent Priorities
**Query**: *"What are the highest priority items that need attention right now?"*  
**Latency**: `6.25s` | **Context Nodes**: `16`  

**Output**:
Here are the top priority action items assigned to you that require your immediate attention, along with an upcoming organizational deadline:

1. **Resolve Saved/Rejected Timecards in Salesforce**
   - **Owner:** You (Michael Baylard)
   - **Details:** BizOps flagged that you have timecard submissions currently in 'Saved' or 'Rejected' status requiring review and submission in the Salesforce Services Delivery Workspace.
   - **Links:** [🔷 View Jira MDP-27](https://michael-baylard.atlassian.net/browse/MDP-27) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a03338fd1849007)

2. **Update Professional Services Profile Slide**
   - **Owner:** You (Michael Baylard)
   - **Details:** Requested by Katrisa Brock to update your technical skill set and photo in the team slide deck for Google's Flex program staffing.
   - **Links:** [📊 Open Google Slides](https://docs.google.com/presentation/d/1hw1J48S0dVxfZ09n1GJerQmt1z7PTN_fbxRiJy1I1bo/edit?disco=AAACFxAZSzg&usp=comment_email_document&ts=6a84c96e&usp_dm=false) | [🔷 View Jira MDP-26](https://michael-baylard.atlassian.net/browse/MDP-26) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a016b2dae26facc)

3. **Submit Identity Verification for Empower HSA Enrollment**
   - **Owner:** You (Michael Baylard)
   - **Deadline:** October 21, 2026
   - **Details:** Optum Bank requires a copy of your Social Security card and unexpired government-issued photo ID to complete HSA enrollment and avoid cancellation.
   - **Links:** [📄 Open Optum Form](https://memberforms.optum.com/HSAEnroll.html) | [🔷 View Jira MDP-25](https://michael-baylard.atlassian.net/browse/MDP-25) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a00f4f947cf534a)

4. **Update PSA Skills & Certifications (Delivery Compliance)**
   - **Owner:** Technical Associates
   - **Deadline:** August 26, 2026 (EOD)
   - **Details:** Mandatory addition of technical skills and certifications into PSA for RMG allocation and L&D compliance.
   - **Links:** [🔷 View Jira MDP-30](https://michael-baylard.atlassian.net/browse/MDP-30) | [✉️ Open Email in Gmail](https://mail.google.com/mail/u/0/#all/1a032dd7a64fb34f)

---

### Scenario 10: Negative Grounding Check
**Query**: *"What was the budget approved for the Q4 Kubernetes multi-cloud migration?"*  
**Latency**: `7.17s` | **Context Nodes**: `16`  

**Output**:
I reviewed your meeting history, decisions, and task records, but found no mention or record of an approved budget for a Q4 Kubernetes multi-cloud migration.

---
