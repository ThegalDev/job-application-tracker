let recentApplications = [];

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "log_application") {
        const data = request.data;
        const now = Date.now();

        // 1. Clean up old entries (older than 20 minutes)
        recentApplications = recentApplications.filter(app => (now - app.time) < 1200000);

        // 2. Check for Duplicates
        // We check if we've logged an application for this Company + Role recently.
        const isDuplicate = recentApplications.some(app =>
            app.company === data.company &&
            app.role === data.role
        );

        if (isDuplicate) {
            console.log(`Duplicate application detected for ${data.company} - ${data.role}. Skipping.`);
            return;
        }

        console.log("Logging application:", data);

        fetch('http://localhost:8000/log', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
            .then(response => {
                if (response.ok) {
                    console.log("Successfully logged.");

                    // Add to recent list
                    recentApplications.push({
                        company: data.company,
                        role: data.role,
                        time: now
                    });

                    // Try System Notification
                    chrome.notifications.create({
                        type: 'basic',
                        iconUrl: 'icon.png',
                        title: 'Job Application Logged',
                        message: `Applied to ${data.role} at ${data.company}`,
                        priority: 2,
                        requireInteraction: true
                    }, (notificationId) => {
                        if (chrome.runtime.lastError) {
                            console.error("Notification Error:", chrome.runtime.lastError);
                        }
                    });

                    // Fallback: In-page Alert (in case notifications are blocked/hidden)
                    // We check if the tab is still open before trying
                    if (sender.tab && sender.tab.id) {
                        chrome.scripting.executeScript({
                            target: { tabId: sender.tab.id },
                            func: (company) => {
                                // Create a small non-intrusive toast in the DOM instead of a blocking alert
                                const div = document.createElement('div');
                                div.style.position = 'fixed';
                                div.style.bottom = '20px';
                                div.style.right = '20px';
                                div.style.backgroundColor = '#4CAF50';
                                div.style.color = 'white';
                                div.style.padding = '15px';
                                div.style.borderRadius = '5px';
                                div.style.zIndex = '999999';
                                div.style.fontFamily = 'Arial, sans-serif';
                                div.style.boxShadow = '0 4px 8px rgba(0,0,0,0.2)';
                                div.innerText = `Job Logged: ${company}`;
                                document.body.appendChild(div);
                                setTimeout(() => div.remove(), 3000);
                            },
                            args: [data.company]
                        }).catch(() => {
                            // Tab might be closed, ignore error
                        });
                    }
                }
            })
            .catch(error => console.error("Error:", error));
    }
});
