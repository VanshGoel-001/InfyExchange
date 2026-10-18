import {createContext,useContext,useEffect,useState} from 'react';
import {api} from '../services/api';
const AuthContext=createContext(null);
export function AuthProvider({children}){const [token,setToken]=useState(()=>localStorage.getItem('infy_token')), [user,setUser]=useState(null),[loading,setLoading]=useState(true); useEffect(()=>{if(!token){setLoading(false);return;} api.me(token).then(setUser).catch(()=>{localStorage.removeItem('infy_token');setToken(null)}).finally(()=>setLoading(false))},[token]); const login=async credentials=>{const data=await api.login(credentials);localStorage.setItem('infy_token',data.access_token);setToken(data.access_token);const profile=await api.me(data.access_token);setUser(profile);return profile}; const logout=()=>{localStorage.removeItem('infy_token');setToken(null);setUser(null)}; return <AuthContext.Provider value={{token,user,loading,login,logout,setUser}}>{children}</AuthContext.Provider>}
export const useAuth=()=>useContext(AuthContext);
