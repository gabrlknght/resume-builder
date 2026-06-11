/* Form handling utilities */

export function collectFormData(sections, sectionFiles) {
  const payload = {};
  for (const section in sectionFiles) {
    payload[section] = sections[section] || {};
  }
  return payload;
}

export function getNestedValue(obj, path) {
  return path.split(".").reduce((acc, part) => acc?.[part], obj);
}

export function setNestedValue(obj, path, value) {
  const parts = path.split(".");
  let current = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    current[part] = current[part] || {};
    current = current[part];
  }
  current[parts[parts.length - 1]] = value;
}

export function createArrayItem(defaultValue = {}) {
  return JSON.parse(JSON.stringify(defaultValue));
}

export function moveArrayItem(array, fromIndex, toIndex) {
  const newArray = [...array];
  const [item] = newArray.splice(fromIndex, 1);
  newArray.splice(toIndex, 0, item);
  return newArray;
}

export function removeArrayItem(array, index) {
  return array.filter((_, i) => i !== index);
}

export function addArrayItem(array, item) {
  return [...array, item];
}
