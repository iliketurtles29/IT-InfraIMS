/*
 * GEMS IT - Django asset page enhancements
 *
 * The database and Django views remain the source of truth.
 * Asset assignment and editing use normal HTML POST forms.
 * No JSON, fetch(), AJAX, or JsonResponse is used.
 */

(() => {
    "use strict";

    document.addEventListener("DOMContentLoaded", () => {
        initializeBootstrapComponents();
        initializeMobileNavigation();
        initializeAssetFilters();
        initializeAssetExport();
        initializeAssetModals();
        initializeFormConfirmations();
    });

    // ---------------------------------------------------------------
    // Bootstrap widgets
    // ---------------------------------------------------------------

    function initializeBootstrapComponents() {
        if (typeof bootstrap === "undefined") return;

        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((element) => {
            bootstrap.Tooltip.getOrCreateInstance(element);
        });

        document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
            bootstrap.Popover.getOrCreateInstance(element);
        });
    }

    // ---------------------------------------------------------------
    // Mobile navigation
    // ---------------------------------------------------------------

    function initializeMobileNavigation() {
        const menuButton = document.querySelector("[data-mobile-menu]");
        const sidebar = document.querySelector(".sidebar");
        const overlay = document.querySelector("[data-sidebar-overlay]");

        if (!menuButton || !sidebar) return;

        const closeSidebar = () => {
            sidebar.classList.remove("is-open");
            overlay?.classList.remove("is-visible");
            document.body.classList.remove("sidebar-open");
        };

        menuButton.addEventListener("click", () => {
            sidebar.classList.toggle("is-open");
            overlay?.classList.toggle("is-visible");
            document.body.classList.toggle("sidebar-open");
        });

        overlay?.addEventListener("click", closeSidebar);

        sidebar.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", closeSidebar);
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth >= 992) closeSidebar();
        });
    }

    // ---------------------------------------------------------------
    // Client-side asset filters
    // ---------------------------------------------------------------

    function initializeAssetFilters() {
        const search = document.querySelector("#assetSearch");
        const status = document.querySelector("#assetStatusFilter");
        const table = document.querySelector("#assetTable");

        if (!table) return;

        search?.addEventListener("input", applyAssetFilters);
        status?.addEventListener("change", applyAssetFilters);
    }

    function applyAssetFilters() {
        const table = document.querySelector("#assetTable");
        const searchTerm = normalize(
            document.querySelector("#assetSearch")?.value
        );
        const selectedStatus =
            document.querySelector("#assetStatusFilter")?.value || "";
        const resultCount = document.querySelector("#assetResultCount");

        if (!table) return;

        const rows = Array.from(
            table.querySelectorAll("tbody tr[data-asset-row]")
        );

        let visibleCount = 0;

        rows.forEach((row) => {
            const matchesSearch =
                !searchTerm || normalize(row.textContent).includes(searchTerm);
            const matchesStatus =
                !selectedStatus || row.dataset.status === selectedStatus;
            const isVisible = matchesSearch && matchesStatus;

            row.classList.toggle("d-none", !isVisible);

            if (isVisible) visibleCount += 1;
        });

        updateEmptyState(table, visibleCount);

        if (resultCount) {
            resultCount.textContent =
                `${visibleCount} asset${visibleCount === 1 ? "" : "s"} found`;
        }
    }

    function updateEmptyState(table, visibleCount) {
        let emptyRow = table.querySelector("tbody tr[data-filter-empty]");

        if (visibleCount > 0) {
            emptyRow?.remove();
            return;
        }

        if (emptyRow) return;

        const columnCount = table.querySelectorAll("thead th").length || 1;

        emptyRow = document.createElement("tr");
        emptyRow.dataset.filterEmpty = "true";
        emptyRow.innerHTML = `
            <td colspan="${columnCount}" class="text-center py-5">
                No assets match the current filters.
            </td>
        `;

        table.querySelector("tbody")?.appendChild(emptyRow);
    }

    // ---------------------------------------------------------------
    // CSV export
    // ---------------------------------------------------------------

    function initializeAssetExport() {
        document
            .querySelector("[data-export-assets]")
            ?.addEventListener("click", () => {
                const table = document.querySelector("#assetTable");
                if (!table) return;

                const headers = Array.from(
                    table.querySelectorAll("thead th")
                )
                    .slice(0, -1)
                    .map((cell) => cleanText(cell.textContent));

                const rows = Array.from(
                    table.querySelectorAll(
                        "tbody tr[data-asset-row]:not(.d-none)"
                    )
                ).map((row) =>
                    Array.from(row.querySelectorAll("td"))
                        .slice(0, -1)
                        .map((cell) => cleanText(cell.textContent))
                );

                if (!rows.length) {
                    showToast("There are no visible assets to export.");
                    return;
                }

                const csv = [headers, ...rows]
                    .map((row) => row.map(csvEscape).join(","))
                    .join("\n");

                const blob = new Blob([csv], {
                    type: "text/csv;charset=utf-8;",
                });
                const downloadUrl = URL.createObjectURL(blob);
                const link = document.createElement("a");

                link.href = downloadUrl;
                link.download = "gems-assets.csv";
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(downloadUrl);

                showToast("Asset CSV export downloaded.");
            });
    }

    // ---------------------------------------------------------------
    // Asset modals
    // ---------------------------------------------------------------

    function initializeAssetModals() {
        document.querySelectorAll("[data-modal-action]").forEach((trigger) => {
            trigger.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();

                openAssetModal(
                    trigger.dataset.modalAction,
                    trigger.dataset.assetTag || ""
                );
            });
        });
    }

    // ---------------------------------------------------------------
    // Form confirmation modal
    // ---------------------------------------------------------------

    function initializeFormConfirmations() {
        document.addEventListener("submit", (event) => {
            const form = event.target;

            if (!(form instanceof HTMLFormElement)) return;

            const isAddForm = form.closest("#addAssetModal");
            const isAssetActionForm = form.id === "assetModalForm";

            if (!isAddForm && !isAssetActionForm) return;

            // Allow the confirmed submission to pass through normally.
            if (form.dataset.confirmedSubmit === "true") {
                delete form.dataset.confirmedSubmit;
                return;
            }

            event.preventDefault();

            const action = form.dataset.confirmAction || (
                isAddForm ? "create" : "save"
            );
            const assetTag = form.querySelector(
                'input[name="asset_tag"]'
            )?.value || "";

            showFormConfirmation({
                title: confirmationTitle(action),
                message: confirmationMessage(action, assetTag),
                confirmLabel: confirmationButtonLabel(action),
                onConfirm: () => {
                    form.dataset.confirmedSubmit = "true";

                    if (typeof form.requestSubmit === "function") {
                        form.requestSubmit();
                    } else {
                        form.submit();
                    }
                },
            });
        });
    }

    function showFormConfirmation({
        title,
        message,
        confirmLabel,
        onConfirm,
    }) {
        let modalElement = document.querySelector("#formConfirmationModal");

        if (!modalElement) {
            modalElement = document.createElement("div");
            modalElement.id = "formConfirmationModal";
            modalElement.className = "modal fade";
            modalElement.tabIndex = -1;
            modalElement.setAttribute("aria-hidden", "true");
            modalElement.innerHTML = `
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" data-confirmation-title></h5>
                            <button
                                type="button"
                                class="btn-close"
                                data-bs-dismiss="modal"
                                aria-label="Close"
                            ></button>
                        </div>
                        <div class="modal-body" data-confirmation-message></div>
                        <div class="modal-footer">
                            <button
                                type="button"
                                class="btn btn-light"
                                data-bs-dismiss="modal"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                class="btn btn-primary"
                                data-confirmation-submit
                            ></button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(modalElement);
        }

        const titleElement = modalElement.querySelector(
            "[data-confirmation-title]"
        );
        const messageElement = modalElement.querySelector(
            "[data-confirmation-message]"
        );
        const submitButton = modalElement.querySelector(
            "[data-confirmation-submit]"
        );

        if (!titleElement || !messageElement || !submitButton) return;

        titleElement.textContent = title;
        messageElement.textContent = message;
        submitButton.textContent = confirmLabel;

        // Replace the previous one-time handler so repeated confirmations
        // always submit only the current form.
        submitButton.onclick = () => {
            onConfirm();

            if (typeof bootstrap !== "undefined") {
                bootstrap.Modal.getOrCreateInstance(modalElement).hide();
            }
        };

        if (typeof bootstrap !== "undefined") {
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
        } else if (window.confirm(message)) {
            onConfirm();
        }
    }

    function confirmationTitle(action) {
        return {
            create: "Create asset",
            save: "Save changes",
            assign: "Assign asset",
            transfer: "Transfer asset",
            return: "Return asset",
            repair: "Complete repair",
        }[action] || "Confirm action";
    }

    function confirmationMessage(action, assetTag) {
        const assetText = assetTag ? ` for ${assetTag}` : "";

        return {
            create: "Are you sure you want to create this asset?",
            save: `Are you sure you want to save these changes${assetText}?`,
            assign: `Are you sure you want to assign this asset${assetText}?`,
            transfer: `Are you sure you want to transfer this asset${assetText}?`,
            return: `Are you sure you want to return this asset${assetText}?`,
            repair: `Are you sure you want to mark this asset as repaired${assetText}?`,
        }[action] || "Are you sure you want to continue?";
    }

    function confirmationButtonLabel(action) {
        return {
            create: "Create asset",
            save: "Save changes",
            assign: "Assign asset",
            transfer: "Transfer asset",
            return: "Return asset",
            repair: "Complete repair",
        }[action] || "Confirm";
    }

    function openAssetModal(action, assetTag) {
        const modalElement = document.querySelector("#assetModal");
        const title = document.querySelector("#assetModalTitle");
        const body = document.querySelector("#assetModalBody");
        const footer = document.querySelector("#assetModalFooter");

        if (!modalElement || !title || !body || !footer) return;

        title.textContent = modalTitle(action);
        body.innerHTML = modalBody(action, assetTag);

        if (action === "return") {
            initializeReturnConditionGuidance(body);
        }

        const form = body.querySelector("#assetModalForm");

        if (form && action === "assign") {
            const urlTemplate = window.assetAssignUrlTemplate || "";

            if (!urlTemplate) {
                console.error(
                    "assetAssignUrlTemplate is missing from assets.html."
                );
            } else {
                form.action = urlTemplate.replace(
                    "__ASSET_TAG__",
                    encodeURIComponent(assetTag)
                );
                form.method = "post";
            }
        }

        if (form && action === "edit") {
            const urlTemplate = window.assetUpdateUrlTemplate || "";

            if (!urlTemplate) {
                console.error(
                    "assetUpdateUrlTemplate is missing from assets.html."
                );
            } else {
                form.action = urlTemplate.replace(
                    "__ASSET_TAG__",
                    encodeURIComponent(assetTag)
                );
                form.method = "post";
            }
        }

        if (form && action === "transfer") {
            const urlTemplate = window.assetTransferUrlTemplate || "";

            if (!urlTemplate) {
                console.error(
                    "assetTransferUrlTemplate is missing from assets.html."
                );
            } else {
                form.action = urlTemplate.replace(
                    "__ASSET_TAG__",
                    encodeURIComponent(assetTag)
                );
                form.method = "post";
            }
        }

        if (form && action === "return") {
            const urlTemplate = window.assetReturnUrlTemplate || "";

            if (!urlTemplate) {
                console.error(
                    "assetReturnUrlTemplate is missing from the page."
                );
            } else {
                form.action = urlTemplate.replace(
                    "__ASSET_TAG__",
                    encodeURIComponent(assetTag)
                );
                form.method = "post";
            }
        }

        if (form && action === "repair") {
            const urlTemplate = window.assetRepairUrlTemplate || "";

            if (!urlTemplate) {
                console.error(
                    "assetRepairUrlTemplate is missing from the page."
                );
            } else {
                form.action = urlTemplate.replace(
                    "__ASSET_TAG__",
                    encodeURIComponent(assetTag)
                );
                form.method = "post";
            }
        }

        footer.innerHTML = `
            <button
                type="button"
                class="btn btn-light"
                data-bs-dismiss="modal"
            >
                Cancel
            </button>
            ${action === "view" ? "" : `
                <button
                    type="${action === "assign" || action === "edit" || action === "transfer" || action === "return" || action === "repair" ? "submit" : "button"}"
                    class="btn ${action === "retire" ? "btn-danger" : "btn-primary"}"
                    ${action === "assign" || action === "edit" || action === "transfer" || action === "return" || action === "repair" ? 'form="assetModalForm"' : ""}
                    data-modal-submit
                >
                    ${submitLabel(action)}
                </button>
            `}
        `;

        if (action !== "assign" && action !== "edit" && action !== "transfer" && action !== "return" && action !== "repair") {
            footer
                .querySelector("[data-modal-submit]")
                ?.addEventListener("click", () => {
                    submitModal(action, assetTag);
                });
        }

        if (typeof bootstrap !== "undefined") {
            bootstrap.Modal.getOrCreateInstance(modalElement).show();
        }
    }

    function modalTitle(action) {
        return {
            add: "Add asset",
            edit: "Edit asset",
            assign: "Assign asset",
            return: "Return asset",
            transfer: "Transfer asset",
            retire: "Retire asset",
        }[action] || "Asset";
    }

    function submitLabel(action) {
        return {
            add: "Create asset",
            edit: "Save changes",
            assign: "Assign asset",
            return: "Return asset",
            transfer: "Transfer asset",
            retire: "Retire asset",
        }[action] || "Save";
    }

    function modalBody(action, assetTag) {
        if (action === "assign") {
            return assignModalBody(assetTag);
        }

        if (action === "transfer") {
            return transferModalBody(assetTag);
        }

        if (action === "return") {
            return returnModalBody(assetTag);
        }

        if (action === "repair") {
            return repairModalBody(assetTag);
        }

        if (action === "edit") {
            return editModalBody(assetTag);
        }

        if (action === "retire") {
            return `
                <div class="alert alert-warning mb-0">
                    Are you sure you want to retire
                    <strong>${escapeHtml(assetTag)}</strong>?
                </div>
            `;
        }

        return `
            <div class="text-muted">
                Action: <strong>${escapeHtml(action)}</strong>
            </div>
        `;
    }

    function getAssetData(assetTag) {
        const row = Array.from(
            document.querySelectorAll("[data-asset-row]")
        ).find((candidate) => candidate.dataset.assetTag === assetTag);

        if (row) {
            return {
                assetTag: row.dataset.assetTag || assetTag,
                assetType: row.dataset.assetType || "Asset",
                brand: row.dataset.brand || "",
                model: row.dataset.model || "",
                serial: row.dataset.serial || "",
                condition: row.dataset.condition || "new",
                purchaseDate: row.dataset.purchaseDate || "",
                warranty: row.dataset.warranty || "",
                department: row.dataset.department || "",
                location: row.dataset.location || "",
            };
        }

        if (
            window.currentAsset &&
            window.currentAsset.assetTag === assetTag
        ) {
            return window.currentAsset;
        }

        return null;
    }

    function editModalBody(assetTag) {
        const assetData = getAssetData(assetTag);

        if (!assetData) {
            return `
                <div class="alert alert-danger mb-0">
                    Asset not found.
                </div>
            `;
        }

        const assetTypes = Array.isArray(window.assetTypes)
            ? window.assetTypes
            : [];
        const departments = Array.isArray(window.assetDepartments)
            ? window.assetDepartments
            : [];
        const locations = Array.isArray(window.assetLocations)
            ? window.assetLocations
            : [];

        const optionMarkup = (items, selectedValue) => items
            .map((item) => `
                <option
                    value="${escapeHtml(item.name)}"
                    ${item.name === selectedValue ? "selected" : ""}
                >
                    ${escapeHtml(item.name)}
                </option>
            `)
            .join("");

        const condition = assetData.condition || "new";

        return `
            <form
                id="assetModalForm"
                method="post"
                data-confirm-action="save"
                novalidate
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value="${escapeHtml(getCsrfToken())}"
                >

                <div class="row g-3">
                    <div class="col-md-6">
                        <label for="editAssetTag" class="form-label">
                            Asset Tag <span class="text-danger">*</span>
                        </label>
                        <input
                            id="editAssetTag"
                            class="form-control"
                            value="${escapeHtml(assetTag)}"
                            readonly
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="editAssetType" class="form-label">
                            Asset Type <span class="text-danger">*</span>
                        </label>
                        <select
                            id="editAssetType"
                            name="asset_type"
                            class="form-select"
                            required
                        >
                            <option value="">Select type</option>
                            ${optionMarkup(assetTypes, assetData.assetType || "")}
                        </select>
                    </div>

                    <div class="col-md-4">
                        <label for="editBrand" class="form-label">Brand</label>
                        <input
                            id="editBrand"
                            name="brand"
                            class="form-control"
                            value="${escapeHtml(assetData.brand)}"
                        >
                    </div>

                    <div class="col-md-4">
                        <label for="editModel" class="form-label">Model</label>
                        <input
                            id="editModel"
                            name="model"
                            class="form-control"
                            value="${escapeHtml(assetData.model)}"
                        >
                    </div>

                    <div class="col-md-4">
                        <label for="editSerial" class="form-label">
                            Serial Number <span class="text-danger">*</span>
                        </label>
                        <input
                            id="editSerial"
                            name="serial_number"
                            class="form-control"
                            value="${escapeHtml(assetData.serial)}"
                            required
                        >
                    </div>

                    <div class="col-md-4">
                        <label for="editCondition" class="form-label">
                            Condition
                        </label>
                        <select
                            id="editCondition"
                            name="condition"
                            class="form-select"
                        >
                            ${conditionOption("new", "New", condition)}
                            ${conditionOption("good", "Good", condition)}
                            ${conditionOption("fair", "Fair", condition)}
                            ${conditionOption("damaged", "Damaged", condition)}
                            ${conditionOption("for_disposal", "For Disposal", condition)}
                        </select>
                    </div>

                    <div class="col-md-4">
                        <label for="editPurchaseDate" class="form-label">
                            Purchase Date
                        </label>
                        <input
                            id="editPurchaseDate"
                            name="purchase_date"
                            type="date"
                            class="form-control"
                            value="${escapeHtml(assetData.purchaseDate)}"
                        >
                    </div>

                    <div class="col-md-4">
                        <label for="editWarranty" class="form-label">
                            Warranty Expiration
                        </label>
                        <input
                            id="editWarranty"
                            name="warranty_expiration"
                            type="date"
                            class="form-control"
                            value="${escapeHtml(assetData.warranty)}"
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="editDepartment" class="form-label">
                            Department <span class="text-danger">*</span>
                        </label>
                        <select
                            id="editDepartment"
                            name="department"
                            class="form-select"
                            required
                        >
                            <option value="">Select department</option>
                            ${optionMarkup(departments, assetData.department || "")}
                        </select>
                    </div>

                    <div class="col-md-6">
                        <label for="editLocation" class="form-label">
                            Location <span class="text-danger">*</span>
                        </label>
                        <select
                            id="editLocation"
                            name="location"
                            class="form-select"
                            required
                        >
                            <option value="">Select location</option>
                            ${optionMarkup(locations, assetData.location || "")}
                        </select>
                    </div>
                </div>
            </form>
        `;
    }

    function conditionOption(value, label, selectedValue) {
        return `
            <option
                value="${value}"
                ${value === selectedValue ? "selected" : ""}
            >
                ${label}
            </option>
        `;
    }

    function transferModalBody(assetTag) {
        const assetData = getAssetData(assetTag);
        const assetType = assetData?.assetType || "Asset";
        const employees = Array.isArray(window.assetEmployees)
            ? window.assetEmployees
            : [];
        const employeeOptions = employees
            .map(
                (employee) => `
                    <option value="${escapeHtml(employee.id)}">
                        ${escapeHtml(employee.name)}
                    </option>
                `
            )
            .join("");
        const today = new Date().toISOString().slice(0, 10);

        return `
            <form
                id="assetModalForm"
                method="post"
                data-confirm-action="transfer"
                novalidate
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value="${escapeHtml(getCsrfToken())}"
                >

                <input
                    type="hidden"
                    name="asset_tag"
                    value="${escapeHtml(assetTag)}"
                >

                <div class="asset-summary mb-4">
                    <strong>${escapeHtml(assetTag)}</strong>
                    <span> · ${escapeHtml(assetType)}</span>
                </div>

                <div class="mb-4">
                    <label for="transferEmployee" class="form-label">
                        Transfer to employee
                        <span class="text-danger">*</span>
                    </label>
                    <select
                        id="transferEmployee"
                        name="employee"
                        class="form-select form-select-lg"
                        required
                    >
                        <option value="">Select employee</option>
                        ${employeeOptions}
                    </select>
                </div>

                <div class="row g-3">
                    <div class="col-md-6">
                        <label for="transferStartDate" class="form-label">
                            Transfer date
                        </label>
                        <input
                            id="transferStartDate"
                            name="start_date"
                            type="date"
                            class="form-control form-control-lg"
                            value="${today}"
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="transferRemarks" class="form-label">
                            Notes
                        </label>
                        <input
                            id="transferRemarks"
                            name="remarks"
                            class="form-control form-control-lg"
                            placeholder="Optional note"
                        >
                    </div>
                </div>
            </form>
        `;
    }

    function returnModalBody(assetTag) {
        const assetData = getAssetData(assetTag);
        const assetType = assetData?.assetType || "Asset";
        const today = new Date().toISOString().slice(0, 10);

        return `
            <form
                id="assetModalForm"
                method="post"
                data-confirm-action="return"
                novalidate
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value="${escapeHtml(getCsrfToken())}"
                >

                <input
                    type="hidden"
                    name="asset_tag"
                    value="${escapeHtml(assetTag)}"
                >

                <div class="asset-summary mb-4">
                    <strong>${escapeHtml(assetTag)}</strong>
                    <span> · ${escapeHtml(assetType)}</span>
                </div>

                <div class="row g-3">
                    <div class="col-md-6">
                        <label for="returnDate" class="form-label">
                            Return date <span class="text-danger">*</span>
                        </label>
                        <input
                            id="returnDate"
                            name="end_date"
                            type="date"
                            class="form-control form-control-lg"
                            value="${today}"
                            required
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="returnedCondition" class="form-label">
                            Returned condition
                        </label>
                        <select
                            id="returnedCondition"
                            name="returned_condition"
                            class="form-select form-select-lg"
                            data-returned-condition
                        >
                            <option value="">Select condition</option>
                            ${conditionOption("new", "New", "")}
                            ${conditionOption("good", "Good", "")}
                            ${conditionOption("fair", "Fair", "")}
                            ${conditionOption("damaged", "Damaged", "")}
                            ${conditionOption("for_disposal", "For Disposal", "")}
                        </select>
                        <div
                            class="form-text d-none"
                            data-return-condition-guidance
                        ></div>
                    </div>

                    <div class="col-12">
                        <label for="returnRemarks" class="form-label">
                            Notes
                        </label>
                        <textarea
                            id="returnRemarks"
                            name="remarks"
                            class="form-control"
                            rows="3"
                            placeholder="Optional note"
                        ></textarea>
                    </div>
                </div>
            </form>
        `;
    }

    function initializeReturnConditionGuidance(container) {
        const conditionSelect = container.querySelector(
            "[data-returned-condition]"
        );
        const guidance = container.querySelector(
            "[data-return-condition-guidance]"
        );

        if (!conditionSelect || !guidance) return;

        const updateGuidance = () => {
            const messages = {
                fair: {
                    text: "Fair condition: add details in Notes and consider an inspection before reissuing this asset.",
                    className: "form-text text-warning",
                },
                damaged: {
                    text: "Damaged: describe the damage in Notes and send the asset for repair or inspection before reuse.",
                    className: "form-text text-danger",
                },
                for_disposal: {
                    text: "For disposal: record the reason in Notes and follow your disposal process. Do not reissue this asset.",
                    className: "form-text text-danger",
                },
            };

            const selected = messages[conditionSelect.value];

            if (!selected) {
                guidance.textContent = "";
                guidance.className = "form-text d-none";
                return;
            }

            guidance.textContent = selected.text;
            guidance.className = selected.className;
        };

        conditionSelect.addEventListener("change", updateGuidance);
        updateGuidance();
    }

    function repairModalBody(assetTag) {
        const assetData = getAssetData(assetTag);
        const assetType = assetData?.assetType || "Asset";
        const today = new Date().toISOString().slice(0, 10);

        return `
            <form
                id="assetModalForm"
                method="post"
                data-confirm-action="repair"
                novalidate
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value="${escapeHtml(getCsrfToken())}"
                >

                <input
                    type="hidden"
                    name="asset_tag"
                    value="${escapeHtml(assetTag)}"
                >

                <div class="asset-summary mb-4">
                    <strong>${escapeHtml(assetTag)}</strong>
                    <span> · ${escapeHtml(assetType)}</span>
                </div>

                <div class="row g-3">
                    <div class="col-md-6">
                        <label for="repairCompletedDate" class="form-label">
                            Repair completed date
                            <span class="text-danger">*</span>
                        </label>
                        <input
                            id="repairCompletedDate"
                            name="completed_date"
                            type="date"
                            class="form-control form-control-lg"
                            value="${today}"
                            required
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="repairCondition" class="form-label">
                            Condition after repair
                            <span class="text-danger">*</span>
                        </label>
                        <select
                            id="repairCondition"
                            name="repaired_condition"
                            class="form-select form-select-lg"
                            required
                        >
                            <option value="good" selected>Good</option>
                            <option value="fair">Fair</option>
                        </select>
                    </div>

                    <div class="col-md-6">
                        <label for="repairVendor" class="form-label">
                            Repair provider
                        </label>
                        <input
                            id="repairVendor"
                            name="repair_provider"
                            class="form-control"
                            placeholder="Optional"
                        >
                    </div>

                    <div class="col-md-6">
                        <label for="repairCost" class="form-label">
                            Repair cost
                        </label>
                        <input
                            id="repairCost"
                            name="repair_cost"
                            type="number"
                            min="0"
                            step="0.01"
                            class="form-control"
                            placeholder="0.00"
                        >
                    </div>

                    <div class="col-12">
                        <label for="repairNotes" class="form-label">
                            Repair details
                            <span class="text-danger">*</span>
                        </label>
                        <textarea
                            id="repairNotes"
                            name="repair_notes"
                            class="form-control"
                            rows="4"
                            placeholder="Describe the repair performed"
                            required
                        ></textarea>
                    </div>
                </div>
            </form>
        `;
    }

    function assignModalBody(assetTag) {
        const row = Array.from(
            document.querySelectorAll("[data-asset-row]")
        ).find((candidate) => candidate.dataset.assetTag === assetTag);

        const assetType = row?.dataset.assetType || "Asset";
        const currentStatus = row?.dataset.status || "available";
        const employees = Array.isArray(window.assetEmployees)
            ? window.assetEmployees
            : [];

        const employeeOptions = employees
            .map(
                (employee) => `
                    <option value="${escapeHtml(employee.id)}">
                        ${escapeHtml(employee.name)}
                    </option>
                `
            )
            .join("");

        const today = new Date().toISOString().slice(0, 10);
        const csrfToken = getCsrfToken();

        return `
            <form
                id="assetModalForm"
                method="post"
                novalidate
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value="${escapeHtml(csrfToken)}"
                >

                <input
                    type="hidden"
                    name="asset_tag"
                    value="${escapeHtml(assetTag)}"
                >

                <div class="asset-summary mb-4">
                    <strong>${escapeHtml(assetTag)}</strong>
                    <span>
                        · ${escapeHtml(assetType)}
                        · current status: ${escapeHtml(currentStatus)}
                    </span>
                </div>

                <div class="mb-4">
                    <label
                        for="assignEmployee"
                        class="form-label"
                    >
                        Assign to employee
                        <span class="text-danger">*</span>
                    </label>

                    <select
                        id="assignEmployee"
                        name="employee"
                        class="form-select form-select-lg"
                        required
                    >
                        <option value="">Select employee</option>
                        ${employeeOptions}
                    </select>
                </div>

                <div class="row g-3">
                    <div class="col-md-6">
                        <label
                            for="assignStartDate"
                            class="form-label"
                        >
                            Start date
                        </label>

                        <input
                            id="assignStartDate"
                            name="start_date"
                            type="date"
                            class="form-control form-control-lg"
                            value="${today}"
                        >
                    </div>

                    <div class="col-md-6">
                        <label
                            for="assignNotes"
                            class="form-label"
                        >
                            Notes
                        </label>

                        <input
                            id="assignNotes"
                            name="remarks"
                            class="form-control form-control-lg"
                            placeholder="Optional note"
                        >
                    </div>
                </div>
            </form>
        `;
    }

    // Non-assign actions remain placeholders until their Django endpoints
    // are added. Assign and edit use the browser's native form submission.
    function submitModal(action, assetTag) {
        const form = document.querySelector("#assetModalForm");

        if (form && !form.checkValidity()) {
            form.reportValidity();
            return;
        }

        showToast(
            `${submitLabel(action)} prepared for ${assetTag || "new asset"}.`
        );
    }

    // ---------------------------------------------------------------
    // CSRF helper
    // ---------------------------------------------------------------

    function getCsrfToken() {
        const csrfCookie = document.cookie
            .split(";")
            .map((cookie) => cookie.trim())
            .find((cookie) => cookie.startsWith("csrftoken="));

        if (csrfCookie) {
            return decodeURIComponent(
                csrfCookie.split("=").slice(1).join("=")
            );
        }

        const csrfInput = document.querySelector(
            "input[name=csrfmiddlewaretoken]"
        );

        return csrfInput?.value || window.assetCsrfToken || "";
    }

    // ---------------------------------------------------------------
    // Shared helpers
    // ---------------------------------------------------------------

    window.showToast = function showToast(message) {
        const toastElement = document.querySelector("#appToast");
        const messageElement = document.querySelector("#toastMessage");

        if (
            !toastElement ||
            !messageElement ||
            typeof bootstrap === "undefined"
        ) {
            return;
        }

        messageElement.textContent = message;
        bootstrap.Toast.getOrCreateInstance(toastElement).show();
    };

    function normalize(value) {
        return String(value || "")
            .toLowerCase()
            .replace(/\s+/g, " ")
            .trim();
    }

    function cleanText(value) {
        return String(value || "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function csvEscape(value) {
        return `"${String(value).replaceAll('"', '""')}"`;
    }

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>'"]/g, (character) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "'": "&#039;",
            '"': "&quot;",
        }[character]));
    }
})();
