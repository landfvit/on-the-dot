(function () {
    const page = document.getElementById("player-page");
    const button = document.getElementById("player-market-value");
    const dateLabel = document.getElementById("player-value-date");
    const dialog = document.getElementById("market-value-dialog");
    let data = null;
    let chart = null;
    const money = value => new Intl.NumberFormat("en-GB", {style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 2}).format(value);
    const formatDate = value => new Date(value).toLocaleDateString("en-GB", {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"});
    document.getElementById("close-market-dialog").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", event => { if (event.target === dialog && (event.offsetX < 0 || event.offsetY < 0 || event.offsetX > dialog.clientWidth || event.offsetY > dialog.clientHeight)) dialog.close(); });
    button.addEventListener("click", () => {
        if (!data?.latest) return;
        dialog.showModal();
        document.getElementById("market-value-subtitle").textContent = `${document.getElementById("player-name").textContent} · ${money(data.latest.value_eur)} · ${formatDate(data.latest.date)}`;
        const source = document.getElementById("market-value-source");
        source.href = data.source_url;
        document.getElementById("market-value-coverage").textContent = `Last available valuation: ${formatDate(data.latest.date)}`;
        const body = document.getElementById("market-history-body");
        body.replaceChildren();
        for (const record of [...data.history].reverse()) {
            const row = document.createElement("tr");
            for (const text of [formatDate(record.date), money(record.value_eur)]) {
                const cell = document.createElement("td");
                cell.textContent = text;
                row.appendChild(cell);
            }
            body.appendChild(row);
        }
        if (chart) chart.destroy();
        if (typeof Chart === "undefined") {
            document.querySelector(".market-chart-container").hidden = true;
            document.querySelector(".market-value-records").open = true;
            return;
        }
        chart = new Chart(document.getElementById("market-value-chart"), {
            type: "line",
            data: {datasets: [{label: "Market value", data: data.history.map(p => ({x: Date.parse(p.date), y: p.value_eur})), borderColor: "#238447", backgroundColor: "#23844718", fill: true, tension: 0, pointRadius: data.history.length > 50 ? 1 : 3, pointHoverRadius: 5, borderWidth: 2}]},
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: {mode: "nearest", intersect: false},
                plugins: {legend: {display: false}, tooltip: {callbacks: {title: points => formatDate(points[0].parsed.x), label: point => money(point.parsed.y)}}},
                scales: {
                    x: {type: "linear", ticks: {maxTicksLimit: 5, callback: value => new Date(value).getUTCFullYear()}, grid: {display: false}},
                    y: {beginAtZero: true, ticks: {maxTicksLimit: 6, callback: money}},
                },
            },
        });
    });
    fetch(`/api/players/${page.dataset.playerId}/market-value`)
        .then(response => { if (!response.ok) throw new Error("Market value request failed"); return response.json(); })
        .then(result => {
            data = result;
            if (!data.available) {
                button.textContent = "Unavailable";
                dateLabel.textContent = "No verified valuation";
                return;
            }
            button.disabled = false;
            button.textContent = money(data.latest.value_eur);
            button.setAttribute("aria-label", `Market value ${money(data.latest.value_eur)}. Open valuation history`);
            dateLabel.textContent = `Transfermarkt · ${formatDate(data.latest.date)}`;
        }).catch(() => { button.textContent = "Unavailable"; dateLabel.textContent = "Could not load valuation"; });
})();
