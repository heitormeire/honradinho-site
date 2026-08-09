(() => {
    const menuButton = document.querySelector("[data-menu-toggle]");
    const navLinks = document.querySelector("[data-nav-links]");

    if (menuButton && navLinks) {
        const closeMenu = () => {
            menuButton.setAttribute("aria-expanded", "false");
            navLinks.classList.remove("is-open");
        };

        menuButton.addEventListener("click", () => {
            const isOpen = menuButton.getAttribute("aria-expanded") === "true";
            menuButton.setAttribute("aria-expanded", String(!isOpen));
            navLinks.classList.toggle("is-open", !isOpen);
        });

        navLinks.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeMenu();
        });
    }

    document.querySelectorAll("[data-current-year]").forEach((element) => {
        element.textContent = String(new Date().getFullYear());
    });

    const searchInput = document.querySelector("[data-command-search]");
    const filters = Array.from(document.querySelectorAll("[data-command-filter]"));
    const cards = Array.from(document.querySelectorAll("[data-command-card]"));
    const sections = Array.from(document.querySelectorAll("[data-command-section]"));
    const count = document.querySelector("[data-command-count]");
    const noResults = document.querySelector("[data-no-results]");

    if (cards.length) {
        let activeFilter = "all";

        const normalize = (value) => value
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();

        const updateResults = () => {
            const query = normalize(searchInput?.value || "");
            let visibleCount = 0;

            cards.forEach((card) => {
                const category = card.dataset.category || "";
                const haystack = normalize(card.textContent || "");
                const matchesFilter = activeFilter === "all" || category === activeFilter;
                const matchesQuery = !query || haystack.includes(query);
                const visible = matchesFilter && matchesQuery;
                card.classList.toggle("is-hidden", !visible);
                if (visible) visibleCount += 1;
            });

            sections.forEach((section) => {
                const hasVisibleCard = Boolean(section.querySelector("[data-command-card]:not(.is-hidden)"));
                section.classList.toggle("is-hidden", !hasVisibleCard);
            });

            if (count) count.textContent = String(visibleCount);
            noResults?.classList.toggle("is-visible", visibleCount === 0);
        };

        filters.forEach((filter) => {
            filter.addEventListener("click", () => {
                activeFilter = filter.dataset.commandFilter || "all";
                filters.forEach((item) => {
                    const selected = item === filter;
                    item.classList.toggle("is-active", selected);
                    item.setAttribute("aria-pressed", String(selected));
                });
                updateResults();
            });
        });

        searchInput?.addEventListener("input", updateResults);
        updateResults();
    }
})();
