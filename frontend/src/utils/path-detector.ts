export const getBasePath = (): string => {
  if (typeof window === 'undefined') {
    return import.meta.env.BASE_URL || '/'
  }

  return import.meta.env.BASE_URL || '/'
}
