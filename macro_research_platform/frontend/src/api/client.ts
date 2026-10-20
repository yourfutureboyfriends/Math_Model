import axios, { AxiosInstance, AxiosError } from 'axios';
import { DashboardData } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        // Error statuses handled by consuming code
        return Promise.reject(error);
      }
    );
  }

  // Dashboard API
  async getDashboardData(): Promise<DashboardData> {
    const response = await this.client.get<DashboardData>('/dashboard');
    return response.data;
  }

  // Regime API - extracted from dashboard
  async getRegimeData() {
    const response = await this.client.get<DashboardData>('/dashboard');
    return response.data.regime;
  }

  // Metrics API - extracted from dashboard
  async getKeyMetrics() {
    const response = await this.client.get<DashboardData>('/dashboard');
    return response.data.keyMetrics;
  }

  // Signals API
  async getSignals() {
    const response = await this.client.get('/signals');
    return response.data;
  }

  // Sector Allocation API - extracted from dashboard
  async getSectorAllocation() {
    const response = await this.client.get<DashboardData>('/dashboard');
    return response.data.sectorAllocation;
  }

  // Risk Indicators API - uses full risk endpoint
  async getRiskIndicators() {
    const response = await this.client.get('/risk/full');
    return response.data;
  }

  // Advanced Indicators API
  async getAdvancedIndicators() {
    const response = await this.client.get('/advanced');
    return response.data;
  }

  // Business Layer API - uses recommendations endpoint
  async getBusinessLayer() {
    const response = await this.client.get('/business/recommendations');
    return response.data;
  }

  // Health check
  async healthCheck(): Promise<{ status: string; mode?: string }> {
    const response = await this.client.get('/health');
    return response.data;
  }

  // Generic POST method
  async post<T = any>(url: string, data: any): Promise<{ data: T }> {
    return this.client.post(url, data);
  }
}

export const api = new ApiClient();
