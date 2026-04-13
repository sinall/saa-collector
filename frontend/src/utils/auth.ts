const TOKEN_KEY = 'token'
const USERNAME_KEY = 'username'
const AVATAR_URL_KEY = 'avatarUrl'

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

  getUsername(): string {
    return localStorage.getItem(USERNAME_KEY) || ''
  },

  setUsername(username: string): void {
    localStorage.setItem(USERNAME_KEY, username)
  },

  getAvatarUrl(): string {
    return localStorage.getItem(AVATAR_URL_KEY) || ''
  },

  setAvatarUrl(url: string): void {
    localStorage.setItem(AVATAR_URL_KEY, url)
  },

  isAuthenticated(): boolean {
    return !!this.getToken()
  },

  login(token: string, username: string, avatarUrl: string): void {
    this.setToken(token)
    this.setUsername(username)
    this.setAvatarUrl(avatarUrl)
  },

  logout(): void {
    this.removeToken()
    localStorage.removeItem(USERNAME_KEY)
    localStorage.removeItem(AVATAR_URL_KEY)
  }
}

export default auth
