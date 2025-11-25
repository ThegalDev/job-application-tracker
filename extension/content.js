// Robust Content Script for Job Tracker

document.addEventListener('click', (event) => {
    const target = event.target;
    const element = target.closest('button, a, input[type="submit"], span, div[role="button"]');

    if (!element) return;

    // Get text from innerText, value, or aria-label
    let text = (element.innerText || element.value || element.getAttribute('aria-label') || "").toLowerCase();
    text = text.trim(); // Remove whitespace

    // Keywords for SUBMISSION only
    const submitKeywords = [
        'submit application',
        'send application',
        'submit profile',
        'finish application',
        'complete application',
        'submit' // Exact match check handled below, but included for completeness
    ];

    // Check if text contains any keyword OR is exactly "submit"
    const isSubmitButton = submitKeywords.some(keyword => text.includes(keyword));

    if (isSubmitButton && !text.includes('filter')) {
        console.log("Job Tracker: Submit button detected:", text);

        // Scrape Data
        let role = "Unknown Role";
        let company = "Unknown Company";
        const url = window.location.href;

        // 1. Try H1 (Job Title)
        const h1 = document.querySelector('h1');
        if (h1) role = h1.innerText.trim();

        // 2. LinkedIn Specifics
        if (url.includes("linkedin.com")) {
            const companyLink = document.querySelector('.job-details-jobs-unified-top-card__company-name a') ||
                document.querySelector('.job-details-jobs-unified-top-card__subtitle a');

            if (companyLink) {
                company = companyLink.innerText.trim();
            } else {
                const subtitle = document.querySelector('.job-details-jobs-unified-top-card__subtitle');
                if (subtitle) company = subtitle.innerText.split('·')[0].trim();
            }
        }

        // 3. Fallback to Title
        if (company === "Unknown Company" || role === "Unknown Role") {
            const title = document.title;
            const parts = title.split(/ - | \| | at /);
            if (parts.length > 0 && role === "Unknown Role") role = parts[0].trim();
            if (parts.length > 1 && company === "Unknown Company") company = parts[parts.length - 1].trim();
        }

        const logData = {
            company: company,
            role: role,
            url: url,
            date: new Date().toISOString().split('T')[0],
            status: "Applied"
        };

        chrome.runtime.sendMessage({
            action: "log_application",
            data: logData
        });
    }
});
