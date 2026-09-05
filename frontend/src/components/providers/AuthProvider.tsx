"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { User } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";
import { UserProfile } from "@/types";

interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  login: (email: string, pass: string) => Promise<boolean>;
  loginWithGoogle: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  login: async () => false,
  loginWithGoogle: async () => {},
  logout: () => {},
});

const mapSupabaseUserToProfile = (supabaseUser: User): UserProfile => {
  const meta = supabaseUser.user_metadata || {};
  const emailUsername = supabaseUser.email ? supabaseUser.email.split("@")[0] : "User";
  const name = meta.full_name || meta.name || emailUsername;
  return {
    name,
    email: supabaseUser.email ?? "",
    role: meta.role ?? "User",
    avatar: meta.avatar_url || meta.avatar || "",
  };
};

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const supabase = createClient();

    // Check initial user session
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (user) {
        setUser(mapSupabaseUserToProfile(user));
        setIsAuthenticated(true);
      } else {
        setUser(null);
        setIsAuthenticated(false);
      }
      setLoading(false);
    });

    // Subscribe to auth state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser(mapSupabaseUserToProfile(session.user));
        setIsAuthenticated(true);
      } else {
        setUser(null);
        setIsAuthenticated(false);
      }
      setLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!loading) {
      const isPublicRoute =
        pathname === "/login" ||
        pathname === "/signup" ||
        pathname.startsWith("/auth/callback");
      if (!isAuthenticated && !isPublicRoute) {
        router.push("/login");
      } else if (isAuthenticated && isPublicRoute && !pathname.startsWith("/auth/callback")) {
        router.push("/");
      }
    }
  }, [isAuthenticated, pathname, loading, router]);

  const login = async (email: string, pass: string): Promise<boolean> => {
    const supabase = createClient();
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password: pass,
    });

    if (error) {
      throw error;
    }

    if (data.user) {
      setUser(mapSupabaseUserToProfile(data.user));
      setIsAuthenticated(true);
      router.push("/");
      return true;
    }
    return false;
  };

  const loginWithGoogle = async (): Promise<void> => {
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) {
      throw error;
    }
  };

  const logout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    setUser(null);
    setIsAuthenticated(false);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, loginWithGoogle, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);

