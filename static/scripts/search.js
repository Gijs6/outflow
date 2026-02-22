document.addEventListener("DOMContentLoaded", () => {
    const searchcontainers = document.querySelectorAll(".searchcontainer");

    searchcontainers.forEach((searchcontainer) => {
        const input = searchcontainer.querySelector(".searchbar input");
        const result = searchcontainer.querySelector(".search-results");

        function update() {
            if (input.value) {
                fetch(`/search_list?q=${encodeURIComponent(input.value)}`)
                    .then((response) => response.text())
                    .then((html) => {
                        result.style.display = "unset";
                        result.innerHTML = html;
                    })
                    .catch((error) => {
                        console.error("Error fetching HTML:", error);
                    });
            } else {
                result.style.display = "none";
            }
        }

        input.addEventListener("input", () => {
            update();
        });

        update();
    });
    document.addEventListener("click", function (event) {
        searchcontainers.forEach((searchcontainer) => {
            const input = searchcontainer.querySelector(".searchbar input");
            const result = searchcontainer.querySelector(".search-results");
            if (searchcontainer.contains(event.target)) {
                if (input.value) {
                    result.style.display = "unset";
                }
            } else {
                result.style.display = "none";
            }
        });
    });
});
