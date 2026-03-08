const TOKEN_KEY = 'token'

export const auth = {
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY)
  },

  setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token)
  },

  removeToken(): void {
    localStorage.removeItem(TOKEN_KEY)
  },

  isAuthenticated(): boolean {
    return !!this.getToken()
  },

  login(token: string): void {
    this.setToken(token)
  },

  logout(): void {
    this.removeToken()
  }
}

export default auth
