/**
 * Какво изобщо си струва да се праща към `/candidates/upload`.
 *
 * Бекендът остава инстанцията, която решава — той проверява и байтовете, не само
 * обявения тип, и връща 415/413. Проверките тук са учтивост: спестяват на
 * рекрутера едно качване от 10 MB, за да чуе „не приемаме такъв файл". Затова и
 * стойностите са огледало на `settings.max_upload_bytes` и
 * `settings.allowed_upload_types` — при промяна там се сменят и тук.
 */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export const ACCEPTED_TYPES = ["application/pdf", "text/plain"] as const;

/** За атрибута `accept` на input-а — разширенията, които диалогът да предлага. */
export const ACCEPTED_EXTENSIONS = ".pdf,.txt";

const EXTENSION_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  txt: "text/plain",
};

function extensionType(name: string): string | undefined {
  const extension = name.toLowerCase().split(".").pop();
  return extension ? EXTENSION_TYPES[extension] : undefined;
}

/**
 * Дава на файла тип, ако браузърът не е.
 *
 * Случва се при непознато на системата разширение — тогава `file.type` е празен
 * низ и бекендът отказва с 415, макар съдържанието да е наред. Пренавиването с
 * типа по разширение е безопасно: сървърът все едно сверява обявеното с байтовете
 * и хваща сгрешено разширение.
 */
export function normaliseFile(file: File): File {
  if (file.type) return file;

  const inferred = extensionType(file.name);
  if (!inferred) return file;

  return new File([file], file.name, { type: inferred, lastModified: file.lastModified });
}

/** Връща причината за отказ, или null, ако файлът може да се качи. */
export function validateFile(file: File): string | null {
  if (file.size === 0) {
    return "The file is empty.";
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    const megabytes = (file.size / (1024 * 1024)).toFixed(1);
    return `The file is ${megabytes} MB, over the ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB limit.`;
  }

  const type = normaliseFile(file).type;
  if (!ACCEPTED_TYPES.includes(type as (typeof ACCEPTED_TYPES)[number])) {
    return `Only PDF and TXT are accepted. This file is ${type || "of an unrecognised type"}.`;
  }

  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
