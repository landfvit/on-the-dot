(function (root) {
    const completed = new Set(["FT", "AET", "PEN"]);
    const inactive = new Set(["PST", "CANC", "ABD", "AWD", "WO"]);

    function dateKey(value) {
        const date = new Date(value);
        return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0")].join("-");
    }

    function parseDay(key) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(key || "")) return null;
        const date = new Date(`${key}T12:00:00`);
        return dateKey(date) === key ? date : null;
    }

    function sortFixtures(fixtures) {
        return [...fixtures].sort((a, b) =>
            new Date(a.match_date) - new Date(b.match_date) || a.fixture_id - b.fixture_id);
    }

    function defaultDay(fixtures, now = new Date()) {
        const ordered = sortFixtures(fixtures);
        const today = dateKey(now);
        const next = ordered.find(f => !completed.has(f.status) && !inactive.has(f.status)
            && dateKey(f.match_date) >= today);
        const last = ordered.filter(f => completed.has(f.status)).at(-1);
        return next ? dateKey(next.match_date)
            : last ? dateKey(last.match_date)
            : ordered.length ? dateKey(ordered[0].match_date) : today;
    }

    function monthDays(month) {
        const start = new Date(month.getFullYear(), month.getMonth(), 1, 12);
        start.setDate(start.getDate() - (start.getDay() + 6) % 7);
        return Array.from({length: 42}, (_, index) =>
            new Date(start.getFullYear(), start.getMonth(), start.getDate() + index, 12));
    }

    const api = {dateKey, parseDay, sortFixtures, defaultDay, monthDays};
    if (typeof module !== "undefined") module.exports = api;
    else root.FixtureCalendar = api;
})(typeof window !== "undefined" ? window : globalThis);
