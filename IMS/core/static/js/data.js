const inventoryData = document.getElementById('inventoryData');

function readTable(id, fields) {
    const table = document.getElementById(id);

    if (!table) {
        return [];
    }

    return Array.from(table.querySelectorAll("tbody tr")).map(function (row) {
        const values = Array.from(row.cells).map(function (cell) {
            return cell.textContent.trim();
        });

        return fields.reduce(function (item, field, index) {
            item[field] = values[index] || "";
            return item;
        }, {});
    });
}


function readSpans(id) {
    const element = document.getElementById(id);

    if (!element) {
        return [];
    }

    return Array.from(element.querySelectorAll("span")).map(function (span) {
        return span.textContent.trim();
    });
}

const TYPES = readSpans("seedTypes");
const STATUSES = readSpans("seedStatuses");
const departments = readSpans("seedDepartments");
const locations = readSpans("seedLocations");

const INVENTORY_DATA = {
    assets: readTable('seedAssets', [
        'tag',
        'type',
        'brand',
        'model',
        'serial',
        'status',
        'condition',
        'purchaseDate',
        'warranty',
        'department',
        'location',
        'employeeId',
        'notes'
    ]),

    employees: readTable('seedEmployees', [
        'id',
        'name',
        'email',
        'department',
        'location',
        'role'
    ]),

    assignments: readTable('seedAssignments', [
        'id',
        'assetTag',
        'employeeId',
        'startDate',
        'endDate',
        'returnedBy',
        'returnedCondition'
    ]),

    auditLogs: readTable('seedAuditLogs', [
        'id',
        'action',
        'description',
        'user',
        'date'
    ])
};

function getStoredArray(key) {
    try {
        const value = JSON.parse(localStorage.getItem(key) || '[]');
        return Array.isArray(value) ? value : [];
    } catch (error) {
        return [];
    }
}

function hasStoredRows(key) {
    return getStoredArray(key).length > 0;
}

function save(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function seedData() {
    if (!hasStoredRows('assets') && INVENTORY_DATA.assets.length > 0) {
        save('assets', INVENTORY_DATA.assets);
    }

    if (!hasStoredRows('employees') && INVENTORY_DATA.employees.length > 0) {
        save('employees', INVENTORY_DATA.employees);
    }

    if (!hasStoredRows('assignments') && INVENTORY_DATA.assignments.length > 0) {
        save('assignments', INVENTORY_DATA.assignments);
    }

    if (!hasStoredRows('auditLogs') && INVENTORY_DATA.auditLogs.length > 0) {
        save('auditLogs', INVENTORY_DATA.auditLogs);
    }
}

function getAssets() {
    return getStoredArray('assets');
}

function getEmployees() {
    return getStoredArray('employees');
}

function getAssignments() {
    return getStoredArray('assignments');
}

function getLogs() {
    return getStoredArray('auditLogs');
}

function employeeName(id) {
    const employee = getEmployees().find(function (item) {
        return item.id === id;
    });

    return employee ? employee.name : 'Unassigned';
}

function addLog(action, description) {
    const logs = getLogs();

    logs.unshift({
        id: 'LOG' + Date.now(),
        action: action,
        description: description,
        user: 'System Admin',
        date: new Date().toISOString()
    });

    save('auditLogs', logs);
}

seedData();
