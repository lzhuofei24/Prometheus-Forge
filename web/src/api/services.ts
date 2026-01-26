import { apiClient } from './client';

export interface Novel {
  id: string;
  title: string;
  genre?: string;
  summary?: string;
  created_at: string;
}

export interface Chapter {
  id: string;
  novel_id: string;
  index: number;
  title?: string;
  status: string;
  created_at: string;
}

export interface ChapterContent {
  chapter_id: string;
  title?: string;
  status: string;
  content?: string;
  summary?: string;
  critique_data?: any;
  version: number;
  created_at?: string;
}

export interface CreateNovelRequest {
  title: string;
  genre?: string;
  summary?: string;
}

export interface CreateChapterRequest {
  novel_id: string;
  index: number;
  title?: string;
}

export interface SaveChapterRequest {
  content?: string;
  summary?: string;
  title?: string;
}

export interface ImportNovelResponse {
  novel_id: string;
  novel_title: string;
  chapters_count: number;
  chapters: Array<{
    index: number;
    title?: string;
    word_count: number;
  }>;
}

/** 小说列表、详情：写作/阅读助手唯一数据源，仅数据库。 */
export const novelsApi = {
  list: async (): Promise<Novel[]> => {
    const response = await apiClient.get<Novel[]>('/novels');
    return response.data;
  },

  get: async (novelId: string): Promise<Novel> => {
    const response = await apiClient.get<Novel>(`/novels/${novelId}`);
    return response.data;
  },

  create: async (data: CreateNovelRequest): Promise<Novel> => {
    const response = await apiClient.post<Novel>('/novels', data);
    return response.data;
  },

  import: async (file: File, title: string, genre?: string): Promise<ImportNovelResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    if (genre) {
      formData.append('genre', genre);
    }
    const response = await apiClient.post<ImportNovelResponse>('/novels/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};

/** 章节目录、章节内容(正文+大纲)：写作/阅读助手唯一数据源，仅数据库。 */
export const chaptersApi = {
  list: async (novelId: string): Promise<Chapter[]> => {
    const response = await apiClient.get<Chapter[]>(`/novels/${novelId}/chapters`);
    return response.data;
  },

  get: async (novelId: string, chapterIndex: number): Promise<ChapterContent> => {
    const response = await apiClient.get<ChapterContent>(
      `/novels/${novelId}/chapters/${chapterIndex}`
    );
    return response.data;
  },

  create: async (data: CreateChapterRequest): Promise<Chapter> => {
    const response = await apiClient.post<Chapter>('/novels/chapters', data);
    return response.data;
  },

  save: async (novelId: string, chapterIndex: number, data: SaveChapterRequest): Promise<{ success: boolean }> => {
    const response = await apiClient.put<{ success: boolean }>(
      `/novels/${novelId}/chapters/${chapterIndex}`,
      data
    );
    return response.data;
  },

  delete: async (novelId: string, chapterIndex: number): Promise<{ success: boolean }> => {
    const response = await apiClient.delete<{ success: boolean }>(
      `/novels/${novelId}/chapters/${chapterIndex}`
    );
    return response.data;
  },
};
