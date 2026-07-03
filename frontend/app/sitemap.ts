import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

const PUBLIC_ROUTES = ["/", "/sample", "/login", "/signup", "/terms", "/privacy"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PUBLIC_ROUTES.map((route) => ({
    url: `${SITE_URL}${route}`,
    lastModified: new Date(),
  }));
}
