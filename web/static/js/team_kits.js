(async function () {
    const page = document.getElementById("team-page");
    const container = document.getElementById("team-kits");
    function renderLayers(drawing, kit) {
        drawing.replaceChildren();
        drawing.classList.add("pixel");
        if (!kit.layers.length) {
            drawing.classList.add("unavailable");
            drawing.textContent = "Not available";
            return;
        }
        for (const layer of kit.layers) {
            const part = document.createElement("span");
            part.className = "kit-part";
            for (const key of ["left", "top", "width", "height"]) {
                const dimension = key === "top" || key === "height" ? 135 : 100;
                part.style[key] = `${layer[key] / dimension * 100}%`;
            }
            part.style.backgroundColor = layer.color;
            const image = document.createElement("img");
            image.src = layer.image_url;
            image.alt = "";
            image.loading = "lazy";
            image.addEventListener("error", () => {
                drawing.replaceChildren();
                drawing.classList.add("unavailable");
                drawing.textContent = "Image unavailable";
            }, {once: true});
            part.appendChild(image);
            drawing.appendChild(part);
        }
    }
    document.querySelector("#team-kits-title span").textContent = `${page.dataset.season}/${String(Number(page.dataset.season) + 1).slice(-2)}`;
    try {
        const response = await fetch(`/api/teams/${page.dataset.teamId}/kits?season=${page.dataset.season}`);
        if (!response.ok) throw new Error("Kit request failed");
        const data = await response.json();
        container.replaceChildren();
        for (const kit of data.kits) {
            const figure = document.createElement("figure");
            figure.className = "team-kit";
            const drawing = document.createElement("div");
            drawing.className = "team-kit-drawing";
            drawing.setAttribute("role", "img");
            drawing.setAttribute("aria-label", `${kit.label} kit ${page.dataset.season}`);
            if (kit.image_url) {
                drawing.classList.add("pixel");
                const image = document.createElement("img");
                image.src = kit.image_url;
                image.alt = "";
                image.width = 400;
                image.height = 540;
                image.loading = "lazy";
                image.addEventListener("error", () => renderLayers(drawing, kit), {once: true});
                drawing.appendChild(image);
            } else renderLayers(drawing, kit);
            const caption = document.createElement("figcaption");
            caption.textContent = kit.label;
            figure.append(drawing, caption);
            if (kit.layers.length) {
                const credits = document.createElement("details");
                credits.className = "kit-credits";
                const summary = document.createElement("summary");
                summary.textContent = "Sources";
                credits.appendChild(summary);
                const names = ["Left sleeve", "Shirt", "Right sleeve", "Shorts", "Socks"];
                for (const [index, layer] of kit.layers.entries()) {
                    const link = document.createElement("a");
                    link.href = layer.source_url;
                    link.textContent = names[index] || "Pattern";
                    link.title = "Original artwork and license";
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                    credits.appendChild(link);
                }
                figure.appendChild(credits);
            }
            container.appendChild(figure);
        }
        const source = document.getElementById("team-kits-source");
        if (data.source_url) { source.href = data.source_url; source.hidden = false; }
    } catch {
        container.textContent = "Could not load kits.";
    }
})();
