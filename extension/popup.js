document.addEventListener('DOMContentLoaded', async () => {
    // Set default date to today
    document.getElementById('date').valueAsDate = new Date();

    // Get current tab info
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
        document.getElementById('url').value = tab.url;
        // Try to guess company/role from title (simple heuristic)
        const title = tab.title;
        const parts = title.split(/[-|]/); // Split by common separators
        if (parts.length > 0) {
            document.getElementById('role').value = parts[0].trim();
        }
        if (parts.length > 1) {
            document.getElementById('company').value = parts[1].trim();
        }
    }

    document.getElementById('saveBtn').addEventListener('click', async () => {
        const data = {
            company: document.getElementById('company').value,
            role: document.getElementById('role').value,
            url: document.getElementById('url').value,
            date: document.getElementById('date').value,
            status: "Applied"
        };

        const statusDiv = document.getElementById('status');
        statusDiv.textContent = "Sending...";
        statusDiv.className = "";

        try {
            const response = await fetch('http://localhost:8000/log', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                statusDiv.textContent = "Saved successfully!";
                statusDiv.className = "success";
                setTimeout(() => window.close(), 1000);
            } else {
                statusDiv.textContent = "Error saving: " + response.statusText;
                statusDiv.className = "error";
            }
        } catch (error) {
            statusDiv.textContent = "Connection failed. Is the dashboard running?";
            statusDiv.className = "error";
        }
    });
});
