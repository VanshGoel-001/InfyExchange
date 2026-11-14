import {createContext,useContext,useEffect,useState} from 'react';
import {api} from '../services/api';
const AuthContext=createContext(null);
export function AuthProvider({children}){const [token,setToken]=useState(()=>localStorage.getItem('infy_token')), [user,setUser]=useState(null),[loading,setLoading]=useState(true),[authError,setAuthError]=useState(''),[attempt,setAttempt]=useState(0);
useEffect(()=>{
  const handleAuthExpired=()=>{setToken(null);setUser(null)};
  window.addEventListener('auth:expired',handleAuthExpired);
  return ()=>window.removeEventListener('auth:expired',handleAuthExpired);
},[]);
useEffect(()=>{if(!token){setLoading(false);return;} setAuthError('');api.me(token).then(setUser).catch(e=>{/* Only a 401 means the token is bad. A network blip or a 5xx must not log anyone out: keep the token and offer a retry. */if(e.status===401){localStorage.removeItem('infy_token');setToken(null)}else setAuthError(e.message)}).finally(()=>setLoading(false))},[token,attempt]); const login=async credentials=>{const data=await api.login(credentials);localStorage.setItem('infy_token',data.access_token);setToken(data.access_token);const profile=await api.me(data.access_token);setUser(profile);return profile}; const loginWithGoogle=async credential=>{const data=await api.googleLogin(credential);localStorage.setItem('infy_token',data.access_token);setToken(data.access_token);const profile=await api.me(data.access_token);setUser(profile);return profile}; const retryAuth=()=>{setLoading(true);setAttempt(a=>a+1)}; const logout=()=>{localStorage.removeItem('infy_token');setToken(null);setUser(null)}; return <AuthContext.Provider value={{token,user,loading,authError,retryAuth,login,loginWithGoogle,logout,setUser}}>{children}</AuthContext.Provider>}
export const useAuth=()=>useContext(AuthContext);
