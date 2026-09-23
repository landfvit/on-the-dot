(function (root) {
    function formationRows(players, formation) {
        const parsed = players.map(player => {
            const match = /^(\d+):(\d+)$/.exec(player.grid || "");
            return match ? {player, row: Number(match[1]), column: Number(match[2])} : null;
        });
        if (parsed.length && parsed.every(p => p && p.row >= 1 && p.row <= 8 && p.column >= 1 && p.column <= 6)
            && new Set(parsed.map(p => `${p.row}:${p.column}`)).size === players.length) {
            const rows = new Map();
            for (const item of parsed) {
                if (!rows.has(item.row)) rows.set(item.row, []);
                rows.get(item.row).push(item);
            }
            return {estimated: false, rows: [...rows].sort((a, b) => b[0] - a[0])
                .map(([, row]) => row.sort((a, b) => a.column - b.column).map(p => p.player))};
        }
        const counts = /^\d(?:-\d){1,5}$/.test(formation || "") ? formation.split("-").map(Number) : [];
        if (players.length !== 11 || !counts.length || counts.some(n => n < 1 || n > 6)
            || counts.reduce((a, b) => a + b, 0) !== 10) return null;
        const keepers = players.filter(p => p.position === "G");
        if (keepers.length !== 1) return null;
        const outfield = players.filter(p => p !== keepers[0]);
        let offset = 0;
        const rows = [[keepers[0]], ...counts.map(count => {
            const row = outfield.slice(offset, offset + count);
            offset += count;
            return row;
        })];
        return {estimated: true, rows: rows.reverse()};
    }
    if (typeof module !== "undefined") module.exports = {formationRows};
    else root.LineupPositions = {formationRows};
})(typeof window !== "undefined" ? window : globalThis);
