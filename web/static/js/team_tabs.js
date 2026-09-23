(function () {
    const tabs = [...document.querySelectorAll('[data-team-tab]')];
    function activate(name, focus = false) {
        const selected = tabs.find(tab => tab.dataset.teamTab === name) || tabs[0];
        for (const tab of tabs) {
            const active = tab === selected;
            tab.setAttribute('aria-selected', String(active));
            tab.tabIndex = active ? 0 : -1;
            document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
        }
        if (focus) selected.focus();
    }
    for (const [index, tab] of tabs.entries()) {
        tab.addEventListener('click', () => {
            activate(tab.dataset.teamTab);
            history.replaceState(null, '', `#${tab.dataset.teamTab}`);
        });
        tab.addEventListener('keydown', event => {
            const target = {ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1}[event.key];
            if (target === undefined) return;
            event.preventDefault();
            tabs[target].click();
            tabs[target].focus();
        });
    }
    window.addEventListener('hashchange', () => activate(location.hash.slice(1)));
    activate(location.hash.slice(1));
})();
