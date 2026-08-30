/** Малките кукички, които държат зареждането и самоличността на рекрутера. */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api/client";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Зарежда данни и пази трите състояния, които всеки изглед има нужда да покаже.
 *
 * `deps` управлява презареждането — при смяна на роля или филтър. Отговор от
 * изоставена заявка се игнорира, за да не пренапише по-нов резултат.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);

    load()
      .then((result) => {
        if (current) setData(result);
      })
      .catch((cause: unknown) => {
        if (!current) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      })
      .finally(() => {
        if (current) setLoading(false);
      });

    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, loading, error, reload };
}

const RECRUITER_KEY = "cv-screening.recruiter";

/**
 * Кой е рекрутерът пред екрана.
 *
 * Проектът няма аутентикация, а решението изисква име — то влиза в `Decision` и
 * в одита. Затова името се пита веднъж и се пази локално, вместо да се измисля
 * стойност по подразбиране: „system" в графата „кой потвърди" би било лъжа.
 */
export function useRecruiter(): [string, (value: string) => void] {
  const [recruiter, setRecruiter] = useState<string>(() => {
    try {
      return window.localStorage.getItem(RECRUITER_KEY) ?? "";
    } catch {
      return "";
    }
  });

  const update = useCallback((value: string) => {
    setRecruiter(value);
    try {
      window.localStorage.setItem(RECRUITER_KEY, value);
    } catch {
      // Приватен режим или забранени бисквитки — името живее само за сесията.
    }
  }, []);

  return [recruiter, update];
}
