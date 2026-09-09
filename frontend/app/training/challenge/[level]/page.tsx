import Quiz from "@/components/quiz";
export default async function LevelPage({params}:{params:Promise<{level:string}>}) { const {level}=await params; return <Quiz mode="challenge" level={Number(level)}/>; }
