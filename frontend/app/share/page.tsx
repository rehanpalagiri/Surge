// Share target feature removed — iOS doesn't support Web Share Target API.
// Any direct visits to /share are redirected to the homepage.
import { redirect } from "next/navigation";

export default function SharePage() {
  redirect("/");
}
